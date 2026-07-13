---

## Task 72: Manual Curve Workflow Rescue, Simple Corner Detection, Loft Overbuild Preview, and Display Customization

Purpose:
The manual curve workflow has become too complicated and still does not behave like the target ExModel-style workflow.

The goal is to simplify and stabilize manual curve creation/editing before adding more primitive fitting or advanced surfacing.

Focus on:

* simple angle-based corner detection
* smooth curve behavior that needs fewer points
* better curve edit/navigation behavior
* less UI clutter
* smaller curve/point display
* color customization
* surface display that does not show internal triangles by default
* loft overbuild preview behavior
* mesh-conforming loft preview for scan/body-line workflows
* removal or consolidation of redundant/useless code where safe

Do not add cylinder/cone/sphere fitting.
Do not add full deviation analysis yet.
Do not add overbuild trimming/intersection yet.
Do not do the large Tasks 78–80 refactor yet.
Do not add proprietary/commercial CAD kernel assumptions.
Use the existing public CAD stack already in the project, currently CadQuery/OCP/OCCT-based.

---

## Important instruction: audit before adding

Before adding new code, inspect the current manual curve, loft, viewport, preferences, and surface-preview code.

If existing code is redundant, unused, misleading, or actively making the tool worse, remove or consolidate it.

Specifically look for:

* duplicate curve modes that behave the same
* user-facing options that do not materially change behavior
* unused helper functions
* repeated corner detection during preview/rendering
* old curve sampling paths that are no longer needed
* UI buttons that are almost always disabled
* display settings hardcoded in viewport files
* surface wireframe/debug display being shown by default
* mesh-conforming preview code, if any, that is mislabeled as CAD/BREP

Rules:

* Do not remove working BREP export.
* Do not remove region select.
* Do not remove curve projection/rebuild/validation.
* Do not remove project save/load compatibility.
* Do not remove old project compatibility.
* If unsure whether a function is used, leave it and add a short TODO comment.
* Do not perform broad package refactoring in this task.
* Keep the changes surgical and workflow-focused.

Acceptance:

* redundant or misleading curve/UI code is removed or hidden where safe
* existing project files still load
* tests pass
* app launches

---

## Part A — Simplify user-facing manual curve modes

The user should not have to choose between several overlapping curve systems.

User-facing curve modes should be reduced to:

1. Smooth Curve
2. Polyline

Optional/legacy/debug modes may remain internally if needed for old project compatibility or tests, but they should not clutter the normal UI.

Smooth Curve:

* default mode
* uses simple angle-based corner detection
* smooths between corners
* preserves sharp corners
* should work for body lines, wheel arches, bumpers, fender contours, and scan guide curves

Polyline:

* straight segment chain
* useful for hard-edged mechanical tracing

Hide/demote:

* Hybrid
* Catmull-Rom
* CAD Spline if it is not a true CAD spline yet

Acceptance:

* normal user sees Smooth Curve and Polyline only
* Smooth Curve is the default
* old curves still load
* old internal modes do not break tests

---

## Part B — Use simple angle-based corner detection only

Corner detection should be simple and cheap, similar to what appears to be used in ExModel-style workflows.

Implement or consolidate into one function:

detect_corner_point_types_by_angle(
control_points,
*,
is_closed: bool,
threshold_degrees: float,
) -> list[str]

Behavior:

* For each eligible point, compute local angle using previous-current-next.
* If angle is below threshold, classify as corner.
* Otherwise classify as smooth.
* Open-curve endpoints should remain smooth unless manually overridden.
* Closed curves may evaluate all points.
* Degenerate/duplicate points should be handled safely.
* No NaN/inf results.
* No expensive mesh queries.
* No curvature optimization.
* No repeated detection inside display sampling.

Default threshold:

* 135 degrees

Performance requirement:

* O(n)
* run only when:

  * a control point is added
  * a control point is deleted
  * a control point is moved
  * the threshold changes
  * the user explicitly presses Auto Detect Corners
* do not run on every viewport render
* do not run during every mouse move unless actively dragging a point, and even then throttle or update only the local affected points if possible

Metadata:

* point_types
* point_type_sources
* corner_angle_threshold_degrees
* control_point_revision
* corner_detection_revision

Point type sources:

* manual
* auto
* legacy
* imported

Rules:

* manually set smooth/corner always overrides auto detection
* auto-detected corners can be cleared
* manual corners must not be cleared by Clear Auto Corners

Acceptance:

* creating manual curves with auto corner detection on is interactive
* detection does not tank performance
* smooth curves are not accidentally over-segmented
* obvious hard angles become corners
* tests verify sampling/rendering does not re-run detection unnecessarily

---

## Part C — Keep smoothing simple and predictable

Do not build a complex tangent-handle system yet.

Use a simple smooth-span approach:

* corners split the curve into spans
* smooth spans are smoothed/interpolated
* corners remain exact
* endpoints remain exact
* closed curves close cleanly

Preferred sampler:

* current best stable smoother if it already works
* otherwise use centripetal Catmull-Rom for smooth spans

Rules:

* smoothing must not cross corner points
* smoothing must not move stored control points
* smoothing affects fitted/display curve only
* smoothness slider controls fitted-curve smoothing strength
* no hidden curve mode behavior
* no excessive control-point creation

Acceptance:

* sparse wheel-arch/body-line curve looks smooth with fewer points
* hard corners stay hard
* smoothness adjustment is visible but predictable
* no performance regression

---

## Part D — Fix manual curve interaction and camera control

Manual curve creation/editing must not trap the user in one camera position.

Required viewport behavior:

* right mouse drag always orbits
* middle mouse drag always pans
* mouse wheel always zooms
* left click only places a point when drawing/add-point mode is active
* left click in edit mode selects a control point only if the cursor is over a control point
* left click empty space in edit mode does nothing
* left drag moves a control point only if the drag starts on a control point
* Esc exits active submode first, then exits curve edit/draw mode if pressed again

Manual curve submodes:

* inactive
* draw_add_points
* edit_select
* edit_move_point
* explicit_add_point
* explicit_insert_point

Rules:

* Creating a new curve starts in draw_add_points.
* Editing an existing curve starts in edit_select.
* Add Point while editing must be explicitly enabled.
* Insert Point while editing must be explicitly enabled.
* Clicking empty space while editing must never add a point.
* Camera navigation must remain available in every submode.

Status text examples:

* "Drawing curve: left-click to add points. Right-drag to orbit."
* "Editing curve: select or drag control points. Right-drag to orbit."
* "Add Point active: left-click to append. Esc returns to edit mode."
* "Insert Point active: click a curve segment. Esc returns to edit mode."

Acceptance:

* user can orbit/pan/zoom during curve drawing
* user can orbit/pan/zoom during curve editing
* no random point placement during navigation
* edit mode does not lock camera control

---

## Part E — Reduce visual size of curve points and lines

The current curve markers and lines are too bulky for scan tracing.

Reduce:

* normal control point radius
* selected control point radius
* minimum control point radius
* active curve line width
* selected curve line width
* preview line width
* surface source curve line width

Suggested defaults:

* selected curve line width: 3.0 to 3.4
* active/manual curve line width: 2.4 to 2.8
* preview line width: 2.0 to 2.2
* control polygon line width: 0.8 to 1.0
* normal control point radius ratio: about 0.0025
* selected point radius ratio: about 0.0040
* minimum point radius: about 0.0015

Visual rules:

* smooth points should be small and readable
* corner points should be visually distinct but not huge
* selected point should be obvious but not block the scan
* control polygon should be thin and muted
* fitted curve should be clear but not thick like a marker

Acceptance:

* points do not obscure scan geometry
* curves look more CAD-like
* selected curves are still visible

---

## Part F — Simplify Manual RE UI

The Manual RE panel currently exposes too many options.

Default visible controls should be:

Manual Curve:

* Create Curve
* Edit Selected Curve
* Finish / Done
* Cancel
* Undo Last Point
* Close / Open Curve
* Convert Selected Curve to Smooth
* Simplify Selected Curve

Basic options:

* Snap to Mesh
* Auto Corners
* Smoothness slider

Move these under a collapsible Advanced Curve Controls section:

* Add Point
* Insert Point
* Delete Point
* Set Point Smooth
* Set Point Corner
* Clear Auto Corners
* Auto Detect Corners
* Straighten Span
* Sample Count
* Corner Threshold
* Debug Curve Method

Rules:

* common workflow should not require opening Advanced
* advanced controls remain available
* disabled buttons should not dominate the UI
* do not redesign the whole app layout in this task

Acceptance:

* Manual RE panel is shorter and easier to understand
* common curve workflow is obvious
* advanced functionality is hidden but available

---

## Part G — Add Preferences color chooser / color wheel

Add general color customization using Tk’s color chooser:

tkinter.colorchooser.askcolor

Add Preferences section:
Display Colors

Color-editable items:

* mesh color
* selected mesh color
* manual curve color
* selected curve color
* active curve color
* smooth point color
* corner point color
* selected point color
* preview point color
* preview line color
* surface color
* selected surface color
* BREP surface color
* selected BREP surface color
* region color
* region edge color
* background color

Colors should be stored and saved across projects. Color wheels should exist in preferences, replacing manual hex inputs.

Rules:

* old settings must load
* invalid colors fall back to defaults
* viewport converts hex colors to RGB
* if live update is safe, apply immediately
* otherwise apply after closing Preferences

Acceptance:

* user can change curve/point/surface colors
* preferences persist
* old settings do not break
* default colors remain reasonable

---

## Part H — Use current public CAD backend only

Use the existing public CAD backend path in the project.

Current intended backend:

* CadQuery/OCP/OCCT

Do not add proprietary CAD kernel assumptions.
Do not add commercial SDK integration.
Do not add unsupported backend UI.

The backend abstraction should remain generic enough for future open/public kernels, but it should only expose capabilities that are actually implemented or planned with the current public stack.

Acceptance:

* CAD/BREP features still work with current installed backend
* app still launches without CAD backend
* STEP export still works when backend is installed
* no confusing unsupported kernel options are added

---

## Part I — Loft overbuild preview and draggable extension handles

ExModel-style lofts appear to overbuild surfaces automatically. Add this as preview/feature behavior first.

Add editable loft options:

* overbuild_enabled: bool = True
* overbuild_amount: float
* overbuild_u_start: float
* overbuild_u_end: float
* overbuild_v_start: float
* overbuild_v_end: float
* show_overbuild_handles: bool = True

Initial implementation:

* extend loft preview beyond source curves by extrapolating sampled surface rows/columns
* store overbuild values in loft feature metadata
* show four corner handles on selected loft preview
* allow dragging handles outward/inward to change overbuild values
* update preview after drag
* mark loft feature dirty/rebuild preview

Important:

* this is not final trim
* this is not surface-surface intersection
* this is not final sewn BREP
* do not claim trimmed/intersected output yet
* if backend cannot create true overbuilt BREP, keep overbuild as preview metadata only

Status text:
"Overbuild preview extends the loft for later trim/intersection. Final trimming is not implemented yet."

Acceptance:

* loft previews overbuild past curve boundaries by default
* user can adjust overbuild with handles
* metadata stores overbuild values
* no false trim/intersection claims
* existing BREP loft export still works

---

## Part J — Hide internal surface triangles by default

Generated surfaces should look like CAD surfaces, not retopology triangle grids.

Default display:

* smooth shaded surface
* no internal triangle wireframe
* boundary edges visible
* optional sparse U/V isocurves
* debug tessellation hidden

Add option:

* Show Surface Tessellation

Rules:

* preview mesh triangles are display-only
* do not show every triangle edge unless debug option is enabled
* BREP/preview surfaces should visually resemble smooth CAD surfaces

Acceptance:

* loft previews look smooth
* internal triangle grid is hidden
* debug wireframe/tessellation can still be enabled

---

## Part K — Mesh-conforming loft preview for open body-line curves

Problem:
Open BREP lofts through body-line curves may not conform to the scanned body. This is expected because a CAD loft interpolates through curves in space; it does not automatically know to follow the mesh between open curves.

Add command:
Create Mesh-Conforming Loft Preview

Behavior:

1. Build a loft sample grid between selected open curves.
2. Project grid points to the nearest mesh surface.
3. Display the projected preview as a smooth shaded surface.
4. Report projection mean/max distance.
5. Store projection metrics.
6. Do not label it as BREP.
7. Do not export it as STEP unless later fitted into a real CAD surface.

Metadata:

* source_curve_ids
* source_mesh_name
* projection_mean_distance
* projection_max_distance
* failed_projection_count
* grid_u_count
* grid_v_count
* conforming_preview = True

Status explanation:
"BREP loft is a clean CAD surface through curves. Mesh-Conforming Preview projects a loft preview to the scan for body-following evaluation."

Acceptance:

* open body-line curves can create a scan-following preview
* user can see whether the surface follows the body
* no false BREP labeling
* projection metrics are shown

---

## Part L — Prepare for future deviation analysis

Do not implement full real-time deviation analysis in this task.

Add only a small module target:

src/analysis/deviation.py

Dataclasses:

* DeviationSample
* DeviationResult

Future concepts:

* curve deviation to mesh
* surface deviation to mesh
* BREP deviation to scan
* color-coded heatmap

Rules:

* no expensive computation yet
* no full UI yet
* no performance hit

Acceptance:

* future deviation analysis has a clear module target
* no current workflow slowdown

---

## Part M — Tests

Add/update tests:

Code cleanup:

* removed/hidden curve modes do not break old project loading
* internal legacy modes still load if needed
* no deleted function breaks imports

Corner detection:

* angle threshold marks sharp corners
* smooth point remains smooth
* open endpoints remain smooth by default
* manual corners override auto
* Clear Auto Corners preserves manual corners
* corner detection does not run during pure sampling/render refresh
* performance with 100+ points is acceptable

Smoothing:

* Smooth Curve is default
* sparse wheel-arch-like curve is smooth
* boxy curve gets corners with auto corners enabled
* smoothing does not cross corners
* endpoints remain exact
* stored control points are not moved by smoothing

Interaction:

* right-drag orbit works in draw mode
* right-drag orbit works in edit mode
* middle-drag pan works in draw/edit mode
* wheel zoom works in draw/edit mode
* left-click empty space in edit mode does not add point
* Add Point mode adds point
* Insert Point mode inserts point
* Esc exits submode predictably

Display:

* reduced line widths applied
* reduced point radius applied
* selected curve still visible
* point markers do not dominate scan

Preferences:

* color chooser saves settings
* invalid color falls back safely
* old settings load
* viewport uses updated colors

CAD backend:

* current CadQuery/OCP/OCCT path still works
* no unsupported/proprietary backend UI added
* STEP export still works if backend installed
* app launches without CAD backend

Loft overbuild:

* loft feature stores overbuild options
* preview extends beyond source curves
* handle drag changes overbuild values
* no trim/intersection claim

Surface display:

* internal triangle wireframe hidden by default
* boundary edges visible
* debug tessellation option works

Mesh-conforming loft:

* projected preview follows mesh
* projection metrics stored
* not exported as BREP
* not mislabeled as CAD/BREP

Regression:

* app launches
* existing manual curves load
* region select works
* BREP face from region works
* BREP loft works
* editable loft feature records still load
* project save/load works
* scene browser works
* pytest passes

Acceptance:

* curve system feels simpler and faster
* corner detection is simple angle-based
* smooth body curves need fewer points
* user can still manually override smooth/corner points
* camera/navigation remain usable
* points and lines are visually smaller
* colors can be adjusted in preferences
* loft overbuild preview exists
* surface triangle grid is hidden by default
* mesh-conforming loft preview exists
* current open-source CAD backend remains functional

## Stop after this task.


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
