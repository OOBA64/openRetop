---

## Task 74: Manual Curve Controller Extraction and Behavior-Preserving Architecture Pass

Purpose:
The manual curve workflow now has substantially better behavior, but its state, input routing, geometry operations, metadata handling, viewport preparation, status messages, and UI synchronization remain embedded directly inside `OpenRetopWindow`.

This makes further curve improvements risky and continues expanding `main_window.py`.

Extract the manual curve workflow into a dedicated, testable controller and session-state system without changing its user-visible behavior.

This is an architecture and stabilization task.

Do not add new manual curve features.
Do not change the current smoothing algorithm.
Do not add tangent handles or NURBS editing.
Do not add primitives.
Do not add surface trimming or intersection.
Do not refactor region selection yet.
Do not refactor surface creation yet.
Do not redesign the UI.
Do not rewrite the viewport.
Do not change project file formats.
Do not fix camera framing in this task.

Known separate issue:

* Frame All and Frame Selected are currently unreliable.
* Loaded projects are not consistently framed around their restored scene.
* That will receive a separate focused task after this extraction.

---

## Part A — Create authoritative manual curve session state

Create:

src/curves/manual_curve_session.py

Add:

ManualCurveSessionState

This must become the authoritative source of transient manual-curve state.

Suggested fields:

Workflow state:

* active: bool
* editing: bool
* edit_curve_id: str | None
* submode: str

Geometry:

* control_points: list[np.ndarray]
* point_types: list[str]
* point_type_sources: list[str]
* is_closed: bool
* curve_method: str
* sample_count: int
* smoothness: int
* preserve_corners: bool

Work-plane state:

* plane_origin: np.ndarray
* plane_normal: np.ndarray
* plane_type: str
* plane_label: str
* source_section_plane_id: str | None

Snapping:

* snap_to_mesh: bool
* keep_curve_on_mesh: bool
* snap_flags: list[bool]
* snap_triangle_indices: list[int | None]
* snap_normals: list[list[float] | None]
* projection_distances: list[float | None]
* snapped_point_count: int

Selection and dragging:

* selected_control_point_index: int | None
* hover_control_point_index: int | None
* drag_candidate_index: int | None
* drag_active: bool
* left_press_position: tuple[int, int] | None
* left_dragged: bool

Placement modes:

* placing_enabled: bool
* add_point_active: bool
* insert_point_active: bool

Preview:

* preview_point: np.ndarray | None
* preview_valid: bool
* preview_snaps_closed: bool
* preview_snaps_to_mesh: bool
* preview_triangle_index: int | None
* preview_normal: list[float] | None

Revisions:

* control_point_revision: int
* corner_detection_revision: int

Required methods:

* reset()
* begin_new_curve(...)
* begin_edit_curve(...)
* exit()
* clear_preview()
* set_preview(...)
* append_point(...)
* insert_point(...)
* remove_point(...)
* move_point(...)
* select_point(...)
* normalize_parallel_arrays()
* mark_controls_changed()
* validate_invariants()
* to_control_data_v2()
* load_control_data_v2(...)

Invariants:

* point type count equals control point count
* point type source count equals control point count
* snap flag count equals control point count
* triangle index count equals control point count
* normal count equals control point count
* projection distance count equals control point count
* selected/hover/drag indices are either valid or None
* snapped_point_count equals the number of true snap flags
* closed curves require at least three points
* all point positions are finite
* plane origin and normal are finite
* plane normal is normalized or safely replaced with a fallback

Do not silently allow parallel arrays to become misaligned.

Acceptance:

* one object owns all transient manual-curve data
* session invariants are directly testable
* no Tk or VTK imports exist in this module

---

## Part B — Create a manual curve workflow controller

Create:

src/app/manual_curve_controller.py

Add:

ManualCurveController

Responsibilities:

* own one `ManualCurveSessionState`
* start a new curve
* load an existing curve for editing
* transition between manual-curve submodes
* append, insert, select, move and delete points
* close/open curves
* maintain corner classifications and revisions
* apply automatic corner detection
* preserve manual corner overrides
* clear only automatically detected corners
* build sampled curve geometry
* build/update `StoredCurve` records
* prepare snapping metadata
* simplify selected curves through existing helpers
* convert selected curves to Smooth Curve
* finish, apply or cancel the workflow
* provide status/diagnostic information to MainWindow

The controller must use existing geometry functions from:

* `curves.manual_curve`
* `curves.curve_state`
* `curves.projection`
* `curves.validation`

Do not duplicate:

* angle corner detection
* smooth-span sampling
* stored-curve construction
* projection implementation
* mesh spatial queries
* curve diagnostics

The controller must not import:

* Tk
* ttk
* messagebox
* file dialogs
* scene browser
* VTK actors
* `OpenRetopWindow`

Use action-result objects rather than direct UI mutations where practical.

Suggested result type:

ManualCurveActionResult

Fields:

* success: bool
* changed: bool
* status: str
* needs_viewport_refresh: bool
* needs_ui_sync: bool
* project_dirty: bool
* created_curve: StoredCurve | None
* updated_curve: StoredCurve | None
* completed_curve_id: str | None
* warnings: tuple[str, ...]
* metadata: dict[str, object]

Acceptance:

* controller behavior can be tested without constructing a Tk window
* controller does not directly manipulate widgets
* controller does not own application-wide selection or project dialogs

---

## Part C — Preserve the current submode behavior

Keep the current submodes:

* inactive
* draw_add_points
* edit_select
* edit_move_point
* explicit_add_point
* explicit_insert_point

Required behavior must remain unchanged:

New curve:

* starts in `draw_add_points`
* left click places a point
* right drag remains camera orbit
* middle drag remains camera pan
* wheel remains camera zoom

Existing curve edit:

* starts in `edit_select`
* clicking empty space does not add a point
* dragging starts only on a control point
* Add Point must be explicitly activated
* Insert Point must be explicitly activated
* Esc exits the current submode before exiting the workflow

The controller should determine whether a left-button event:

* selects a point
* begins a point drag
* places a point
* inserts a point
* does nothing

MainWindow or the viewport adapter may still provide:

* screen-to-work-plane projection
* mesh picking
* screen-space point hit testing
* screen-space curve-segment hit testing

The controller receives the resolved geometric result and updates its session.

Acceptance:

* manual curve input behavior remains identical to Task 72
* right/middle/wheel events are never consumed by the controller
* no random point placement returns

---

## Part D — Integrate the accelerated mesh-query service

Manual curve projection must continue using the per-window:

MeshQueryService

MainWindow should inject or pass the service into controller operations that require it.

Preserve:

* Snap to Mesh point metadata
* Keep Curve On Mesh
* projection triangle indices
* projection normals
* mean/max projection distance
* failed projection indices
* query backend
* index build/query timing
* mesh revision handling

Do not:

* create another global locator
* create one locator per curve
* introduce another mesh cache
* revert to brute-force projection

Acceptance:

* repeated manual-curve projections reuse the window’s spatial index
* transformed mesh revisions still invalidate correctly
* Task 73 mesh-query tests remain valid

---

## Part E — Reduce MainWindow to integration and UI adapters

Replace the manual-curve state fields currently stored directly on `OpenRetopWindow` with:

self.manual_curve_controller

MainWindow should retain only:

* Tk variables
* widget references
* dialogs and context menus
* viewport calls
* scene browser calls
* application selection integration
* undo-stack integration
* project-dirty integration
* work-plane and mesh-pick adapters
* thin command wrappers used by menus and existing tests

Existing command methods may remain as compatibility wrappers, for example:

start_manual_curve_mode()
start_manual_curve_edit_mode()
activate_manual_curve_add_point()
activate_manual_curve_insert_point()
delete_selected_manual_curve_point()
auto_detect_manual_curve_corners()
clear_auto_detected_manual_curve_corners()
apply_manual_curve_edits()
done_manual_curve_editing()

Each wrapper should:

1. gather UI values or external geometry
2. call the controller
3. apply the returned result
4. refresh viewport/UI only when requested

Do not keep duplicated shadow state in MainWindow.

Temporary compatibility properties are acceptable when required by existing tests, but they must directly forward to the controller session.

Example:

@property
def _manual_curve_points(self):
return self.manual_curve_controller.session.control_points

Do not store a second `_manual_curve_points` list.

Acceptance:

* controller/session is the only manual-curve state source
* MainWindow wrappers are small
* manual-curve algorithms no longer exist inside MainWindow
* Tk-specific behavior remains in MainWindow
* no broad unrelated MainWindow refactor occurs

---

## Part F — Extract viewport-state preparation

Add a controller method or pure helper that produces a display snapshot:

ManualCurveDisplayState

Fields:

* active
* editing
* control_points
* point_types
* fitted_points
* is_closed
* plane_normal
* snap_to_mesh
* selected_point_index
* curve_method
* sample_count
* preview_point
* preview_valid
* preview_snaps_closed
* preview_snaps_to_mesh

MainWindow’s `_refresh_viewport()` should request this snapshot instead of rebuilding manual-curve state and fitted geometry inline.

Keep Curve On Mesh projection may occur while producing this snapshot, but:

* it must use the shared mesh query service
* it should avoid recomputation when neither controls nor mesh revision changed
* it must not alter stored control points

Add a small display cache keyed by:

* control point revision
* curve method
* sample count
* smoothness
* point types
* closure state
* Keep Curve On Mesh state
* mesh revision

Acceptance:

* ordinary viewport refreshes do not repeatedly resample or reproject an unchanged manual curve
* moving a point invalidates the display snapshot
* changing smoothing/method/sample count invalidates it
* camera movement alone does not invalidate curve geometry

---

## Part G — Preserve storage and backward compatibility

Do not change the project format.

Preserve existing metadata fields:

* creation_type
* control_points
* control_points_v2
* point_types
* point_type_sources
* corner_angle_threshold_degrees
* control_point_revision
* corner_detection_revision
* curve_method
* sample_count
* smoothness
* preserve_corners
* snap_to_mesh
* snap_mode
* snap_triangle_indices
* snap_normals
* snap_projection_distances
* keep_curve_on_mesh
* source_mesh_name
* source_section_plane_id
* projection statistics
* region/source lineage

Existing legacy curves must still upgrade through the existing parser/storage helpers.

Preserve:

* manual curves
* curve-on-mesh records
* region boundaries converted to editable curves
* projected curves
* rebuilt curves
* old polyline/manual projects
* hidden legacy Hybrid and Catmull-Rom modes

Acceptance:

* old projects load
* save/load round trips retain all manual curve metadata
* editing a restored curve does not erase source lineage

---

## Part H — Preserve undo and dependent-feature rebuild behavior

Manual curve operations must continue participating in undo/redo.

Preserve undo behavior for:

* creating a curve
* applying edits
* deleting points
* converting to Smooth Curve
* simplifying a curve
* changing persistent curve geometry

Preserve source-dependent updates:

* linked editable lofts become dirty
* automatic loft rebuild behavior remains
* four-boundary features become dirty
* surface source selection remains valid

The controller should not own the global undo stack.

It should return before/after records or action information so MainWindow can create the existing undo commands.

Acceptance:

* undo/redo restores geometry and metadata
* editing a loft source still rebuilds or marks the loft dirty
* no dependent feature silently keeps stale geometry

---

## Part I — Remove redundant code after migration

After all callers have moved to the controller/session:

Remove or consolidate:

* duplicated manual curve state initialization
* duplicated reset logic
* duplicated parallel-array maintenance
* duplicated preview-state mutation
* repeated point append/insert/delete bookkeeping
* repeated state-transition conditionals
* repeated fitted-curve construction in MainWindow
* obsolete compatibility helpers with no callers
* unused imports created by extraction

Rules:

* search all references before removing a method
* retain thin compatibility wrappers where external commands/tests use them
* do not game line-count reduction by compressing formatting
* do not move code without improving ownership
* do not delete tests to make the refactor pass

Expected result:

* a meaningful reduction in `main_window.py`
* preferably at least roughly 1,500 lines moved or removed
* exact line count is secondary to correct ownership and behavior

---

## Part J — Tests

Add:

tests/test_manual_curve_session.py
tests/test_manual_curve_controller.py

Session tests:

* defaults are valid
* reset clears all transient state
* begin-new initializes the correct submode
* begin-edit loads all curve metadata
* parallel arrays remain aligned
* invalid selected indices are cleared
* snap count remains accurate
* closing with fewer than three points is rejected
* non-finite points are rejected
* preview reset is complete

Controller workflow tests:

* create open smooth curve
* create closed smooth curve
* create polyline
* load existing curve for editing
* select point
* move point
* append point
* insert point
* delete point
* finish/apply
* cancel
* angle corner detection
* manual corner override
* clear auto corners
* change smoothness
* change sample count
* simplify
* convert to Smooth Curve
* Snap to Mesh metadata
* Keep Curve On Mesh projection
* projection cache reuse

Input-routing tests:

* edit empty-space click does nothing
* drawing click adds point
* explicit Add Point adds point
* explicit Insert Point inserts point
* point drag begins only from a point
* right mouse input is not consumed
* middle mouse input is not consumed
* wheel input is not consumed
* Esc exits submode in the correct order

Integration/regression:

* all existing Task 72 tests pass
* all Task 73 mesh-query tests pass
* existing MainWindow manual-curve tests pass
* region selection still works
* project save/load still works
* BREP creation/export paths still import
* loft source edits still trigger dependent rebuild handling
* preferences still work
* app launches

Add an architectural test or inspection assertion confirming:

* `OpenRetopWindow.__dict__` does not contain independent manual curve point/type/snap arrays
* compatibility properties, if retained, reference controller session data
* `manual_curve_controller.py` imports no Tk or VTK UI classes

---

## Final acceptance

Task 74 is complete when:

* one session object owns transient manual curve state
* one controller owns manual curve workflow behavior
* MainWindow contains only UI/application adapters and thin command wrappers
* no duplicated manual curve state remains
* viewport refresh no longer rebuilds unchanged manual curve geometry
* Task 72 behavior is unchanged
* Task 73 accelerated projection remains in use
* legacy projects still load
* save/load preserves manual curve metadata
* undo/redo still works
* dependent loft/patch features still react to source edits
* all tests pass
* CI passes
* app launches
* no primitives, trimming, camera refactor or unrelated UI redesign was added

## Stop after this task.
