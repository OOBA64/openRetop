---

openRetop Next Phase Instructions
Highly Constrained Tasks 55–61
------------------------------

General execution rules:

* Complete exactly one numbered task at a time.
* Do not skip ahead.
* Do not combine tasks.
* Do not add BREP/STEP/IGES export.
* Do not add new dependencies.
* Do not rewrite the viewport.
* Do not rewrite the scene browser.
* Do not redesign the whole UI.
* Do not rename existing public functions unless required by tests.
* Do not remove working features.
* Prefer small, targeted changes over architecture rewrites.
* Use existing modules first.
* Add new files only when explicitly requested.
* After each task:

  * run pytest
  * launch python src/main.py
  * load a mesh
  * verify scene browser selection still works
  * verify project save/load still works
  * stop

Current confirmed existing features:
[x] Project system
[x] Mesh import/display/proxy
[x] Scene browser/outliner
[x] Preferences/settings/keybind shell
[x] Multiple section planes
[x] Section plane transforms
[x] Arbitrary section slicing
[x] Curve diagnostics
[x] Tiny curve detection
[x] Curve repair: join and auto-close
[x] Curve processing: simplify and smooth
[x] Surface preview system
[x] Explicit Fill Closed Curve command
[x] Explicit Loft Between Two Curves command
[x] Surface preview diagnostics metadata
[x] Scene reset through New Project
[x] Delete Mesh
[x] Undo/Redo foundation
[x] Basic scene browser context menu
[x] Basic visibility hotkeys

Current phase goal:
Move from infrastructure toward usable reverse-engineering workflow without destabilizing the app.

---

## Task 55: Finish scene browser parent visibility and object actions

Goal:
Make the existing scene browser behave like a reliable object manager without rewriting it.

Do not add new geometry tools.
Do not add ViewCube.
Do not add manual curve tools.
Do not touch surface algorithms.
Do not rewrite SceneBrowser.

Current state:

* Scene browser already has individual [V]/[H] labels.
* Individual mesh/plane/result/curve/surface nodes exist.
* Context menu exists.
* Multi-selection exists.
* Parent/group nodes exist.
* Missing: mixed-state parent labels, direct child-aware actions, and complete frame/delete behavior.

Requirements:

1. Parent visibility labels

Add mixed visibility labels to parent/group nodes.

Use these exact prefixes:

* [V] = all visible
* [H] = all hidden
* [M] = mixed visible/hidden

Apply to:

* Section Planes parent
* Section Results parent
* Curves parent
* each Curve group under a Section Result
* Repaired Curves group
* Unassigned curve group
* Surfaces parent

Examples:

* [V] Section Planes
* [M] Curves
* [H] Repaired Curves
* [M] Surfaces

Do not use icon fonts.

2. Parent visibility behavior

Visibility actions on parent/group nodes must operate on their children.

Rules:

* Toggle Section Planes toggles all section planes.
* Hide Section Planes hides all section planes.
* Show Section Planes shows all section planes.
* Isolate Section Planes hides mesh/results/curves/surfaces where supported and shows section planes.
* Toggle Section Results toggles all section results.
* Toggle Curves toggles all curves.
* Toggle curve group toggles only curves in that group.
* Toggle Surfaces toggles all surfaces.

Do not make parent visibility a separate stored state.
Parent state must be derived from children.

3. Context menu labels

Context menu may remain generic, but commands must use the actual selected node set.

Required actions:

* Rename
* Toggle Visibility
* Hide Selected
* Show Selected
* Isolate Selected
* Delete Selected
* Frame Selected

If the existing menu does not include Show Selected, add it.

Rename:

* enabled only when exactly one renameable non-parent object is selected
* disabled for parent/group nodes
* disabled for multi-selection

4. Delete behavior

Delete Selected must work on:

* mesh, with confirmation
* selected section planes
* selected section results
* selected curves
* selected surfaces
* parent/group selections by expanding to child objects

Dependency rules:

* deleting mesh clears all scene data
* deleting a section plane deletes dependent section results, curves, and surfaces
* deleting a section result deletes dependent curves and surfaces
* deleting a curve deletes dependent surfaces
* deleting a surface deletes only that surface

If undo for section plane/result/mesh delete is not safe yet:

* perform the delete safely
* show status
* leave TODO
* do not crash

5. Frame Selected completion

Current frame behavior is too narrow.

Implement frame selected for:

* mesh
* active section plane
* active section result
* active curve
* selected curves
* active surface
* selected surfaces

Minimum acceptable:

* calculate bounds from selected object geometry
* call a viewport method to frame those bounds
* if geometry is missing, show status explaining why

Do not reset transforms.
Do not change object selection.

6. Undo/redo integration

Use the existing UndoStack.

Required undoable actions:

* rename object
* visibility toggle/hide/show
* delete curve
* delete surface

Optional if safe:

* delete section result
* delete section plane

Do not attempt undo for Delete Mesh in this task unless already straightforward.

7. Tests

Add/update tests for:

* parent label [V]
* parent label [H]
* parent label [M]
* toggling Curves parent affects all curves
* toggling curve group affects only that group
* Show Selected restores selected hidden children
* Delete Selected on curve group deletes child curves
* deleting curve deletes dependent surfaces
* Frame Selected handles selected curve
* rename disabled/rejected for parent node
* visibility command can be undone/redone

Acceptance:

* app launches
* parent visibility labels are correct
* parent visibility commands affect child objects
* Show Selected exists
* Delete Selected works from parent/group nodes
* Frame Selected works beyond just mesh/section plane
* existing hotkeys still work
* pytest passes

Stop after this task.

---

## Task 56: Curve viewport display and source-curve highlighting

Goal:
Make curves visually understandable when many generated, repaired, tiny, selected, and surface-source curves exist.

Do not add new curve algorithms.
Do not add manual curve tools.
Do not add mesh snapping.
Do not add region selection.
Do not rewrite surface preview logic.

Current state:

* Curves already have diagnostics.
* Tiny curves already exist.
* Repaired curves already exist through metadata.
* Selected/unselected curve colors exist.
* Missing: distinct repaired/tiny/source/active styling.

Requirements:

1. Add curve style classification

Create a small internal curve display classifier.

Suggested categories:

* hidden
* normal
* tiny
* repaired
* selected
* active
* surface_source
* active_surface_source

Priority order:
hidden < normal < tiny < repaired < surface_source < selected < active

No new dependency.
Do not put large style logic in main_window if viewer module is a better fit.

2. Viewport curve styles

Viewport must visually distinguish:

* normal curves
* selected curves
* active curve
* repaired curves
* tiny curves
* curves used by the selected active surface

Suggested:

* normal: thin muted green/blue
* selected: thick cyan
* active: thick yellow/cyan or brightest available
* repaired: orange/purple
* tiny: muted gray/red
* surface-source: bright secondary overlay

Exact colors are less important than clear difference.

3. Repaired curve detection

Use existing curve metadata.

A curve is repaired if:

* metadata["repair_type"] is "join"
* metadata["repair_type"] is "auto_close"
* metadata["processing_type"] is "simplify", if present
* metadata["processing_type"] is "smooth", if present

If simplify/smooth metadata uses another key, support that key without breaking join/auto_close.

4. Surface source highlighting

When a surface is selected:

* every curve in surface.source_curve_ids should be highlighted even if not selected
* active/selected curve styling still wins
* hidden source curves remain hidden

Do not auto-select source curves just because the surface is selected.

5. Scene browser labels

Improve curve labels without clutter.

Append:

* (tiny)
* (closed)
* (repaired)
* (manual), later if manual metadata exists

Priority:

* tiny first
* repaired second
* closed third

Examples:

* [V] Curve 1 (tiny)
* [V] Joined Curve 1 (repaired)
* [V] Curve 2 (closed)

6. Add command: Select Source Curves

When a surface is selected:

* select all source curves
* active curve should be the first source curve
* status: "Selected source curves for Loft Surface 1"

If no surface selected:

* status: "Select a surface first."

Add to:

* Surfaces menu
* scene browser context action if selected node is surface
* surface context panel if practical

7. Tests

Add/update tests for:

* repaired curve classified as repaired
* tiny curve classified as tiny
* selected curve overrides repaired style
* active curve overrides selected style
* selected surface highlights source curves
* hidden source curve is not rendered
* scene browser curve labels include repaired/tiny/closed
* Select Source Curves selects expected curves

Acceptance:

* app launches
* selected curve is visually obvious
* active curve is visually obvious
* repaired curves are visually distinct
* tiny curves are visually distinct
* selecting a surface highlights its source curves
* Select Source Curves works
* existing curve repair/simplify/smooth still works
* pytest passes

Stop after this task.

---

## Task 57: Surface workflow completion without changing algorithms

Goal:
Finish the existing surface workflow using current preview algorithms.

Do not add NURBS.
Do not add BREP export.
Do not rewrite surface_preview.py unless fixing a direct bug.
Do not add patch networks.
Do not change fill/loft math unless a test proves it is broken.

Current state:

* Fill Closed Curve exists.
* Loft Between Two Curves exists.
* Surface preview diagnostics exist.
* Surface context has source curve names and metadata text.
* Missing: source-curve workflow commands, clearer diagnostics display, surface display controls.

Requirements:

1. Keep current commands

Do not remove:

* Fill Closed Curve
* Loft Between Two Curves
* Create Surface From Selected Curves compatibility alias, if it exists

Do not recreate these commands.
Only fill missing workflow pieces.

2. Add source curve commands

Add surface-source commands:

* Select Source Curves
* Isolate Source Curves
* Show Source Curves
* Frame Source Curves

Behavior:

* require exactly one active surface
* use surface.source_curve_ids
* ignore missing source curves but report them in status
* do not crash if source curves were deleted

Add commands to:

* Surfaces menu
* surface context panel if practical
* scene browser context menu when a surface node is selected if low-risk

3. Surface diagnostics layout

Surface context should show separate, readable fields:

* Name
* Type
* Source curve count
* Source curve names
* Preview available
* Preview reason
* Preview warning
* Resampled point count
* Reversed second curve
* Seam shift applied
* Average pair distance
* Max pair distance

Do not replace this with one huge metadata string only.
Keep raw metadata string optional under "Advanced/Raw metadata" if already present.

4. Surface display controls

Add or connect:

* opacity setting
* selected surface highlight
* wireframe overlay toggle

Constraints:

* opacity must not affect mesh opacity
* hidden surfaces are not rendered
* selected surface remains identifiable even with low opacity

If wireframe overlay is risky:

* add menu/preference placeholder and TODO
* do not fake it with broken rendering

5. Surface grouping in scene browser

Group surfaces by type if low-risk:

Surfaces
Fills
Fill Surface 1
Lofts
Loft Surface 1

If implementing grouping risks breaking selection:

* do not group yet
* instead ensure names are clear:

  * Fill Surface 1
  * Loft Surface 1

6. Undo/redo

Use existing undo stack.

Required:

* create surface undo
* delete surface undo
* rename surface undo
* surface visibility undo

7. Tests

Add/update tests for:

* Select Source Curves
* Isolate Source Curves
* Show Source Curves
* Frame Source Curves
* missing source curves handled safely
* diagnostics fields populated from metadata
* surface opacity value reaches viewport actor if implemented
* create surface undo/redo
* delete surface undo/redo

Acceptance:

* app launches
* selecting a surface explains exactly what created it
* source curve commands work
* surface diagnostics are readable
* surface visibility/opacity controls work or safe placeholders exist
* fill/loft behavior does not regress
* pytest passes

Stop after this task.

---

## Task 58: Named views and lightweight ViewCube shell

Goal:
Add practical named view navigation without destabilizing the VTK viewport.

Do not rewrite camera navigation.
Do not remove current axis gizmo.
Do not add dependencies.
Do not create another VTK render window.
Do not add modeling tools.

Requirements:

1. Add named view commands

Add commands:

* Top
* Bottom
* Front
* Back
* Left
* Right
* Isometric

Add to View menu under a clear section.

2. Camera behavior

Each command must:

* keep current view center
* use current view extent
* set camera position
* set focal point
* set view-up
* reset clipping range
* request exactly one render
* not alter mesh transform
* not alter section planes
* not alter curves/surfaces

3. Viewport API

Add a focused viewport method, for example:

* set_named_view(name: str)
  or individual methods:
* view_top()
* view_front()
* view_right()
* view_isometric()

Do not put camera math directly in menu construction.

4. Lightweight ViewCube shell

Add a non-VTK Tk overlay or simple button panel near top-right of viewport.

Minimum acceptable:

* small panel with buttons:

  * Top
  * Front
  * Right
  * Iso

Preferred:

* also include Left/Back/Bottom through menu only

Do not implement a true 3D cube yet.
Do not use vtkOrientationMarkerWidget.

5. Preferences

Add setting:

* show_viewcube: bool

Preferences → Viewport:

* Show ViewCube

Save/load setting.
Default: True.

6. Performance constraints

ViewCube shell must:

* not render every mouse move
* not create an extra VTK window
* not interfere with picking
* not steal keyboard shortcuts
* not tank empty viewport performance

7. Tests

Add/update tests for:

* named view methods change camera direction
* named view does not change mesh transform
* View menu contains named view commands
* show_viewcube setting saves/loads
* app launches with ViewCube enabled
* app launches with ViewCube disabled

Acceptance:

* app launches
* named views work from View menu
* lightweight ViewCube shell appears if enabled
* no blank VTK output window
* viewport performance does not regress
* pytest passes

Stop after this task.

---

## Task 59: Manual curve creation on active work plane

Goal:
Add the first manual reverse-engineering tool: user-created curves from placed points.

Do not add mesh snapping yet.
Do not add region selection.
Do not add sketch constraints.
Do not add NURBS.
Do not add BREP export.

Requirements:

1. Add manual curve mode

Add mode:

* Curves → Create Manual Curve
  or
* Tools → Manual Curve

When active:

* status says "Manual Curve: click to place points"
* Esc cancels
* Enter confirms
* Backspace deletes last pending point
* C toggles closed/open if point count >= 3

2. Work plane

For this task, point placement occurs on a plane.

Plane selection:

* if an active section plane exists, use its origin/normal
* otherwise use world XY

Status must say:

* "Manual Curve: using Section Plane 2"
  or
* "Manual Curve: using world XY plane"

3. Viewport click projection

Clicking viewport should place a point on the active work plane.

Implementation:

* build a ray from camera through mouse position
* intersect ray with active work plane
* if ray is parallel or invalid, do not add point and show status

Do not require mesh picking in this task.

4. Preview display

While in manual curve mode:

* render pending points
* render temporary polyline
* if closed toggle is active, show closing segment
* status shows point count

Use existing overlay systems where practical.
Do not create permanent StoredCurve until confirmed.

5. Confirm creates StoredCurve

On Enter:

* if fewer than 2 points and open: reject
* if fewer than 3 points and closed: reject
* create StoredCurve
* name: Manual Curve 1, Manual Curve 2, etc.
* original_points = fitted_points
* mean_error = 0
* max_error = 0
* visible = True
* selected = True
* metadata:

  * creation_type: manual
  * work_plane_type: section_plane or world_xy
  * source_section_plane_id if used
  * closed: bool

6. Created curve behavior

Manual curves must:

* appear in scene browser
* be selectable
* be renameable
* hide/show
* deleteable
* save/load
* be usable by Fill Closed Curve
* be usable by Loft Between Two Curves

7. Undo/redo

Creating a manual curve must be undoable/redoable using existing UndoStack.

8. Tests

Add/update tests for:

* manual curve mode starts empty
* adding point appends pending point
* Backspace removes last point
* Esc cancels pending curve
* C toggles closed only when point count >= 3
* Enter rejects too few points
* Enter creates StoredCurve
* manual curve metadata is correct
* manual curve can be used for surface creation
* undo/redo manual curve creation

Acceptance:

* app launches
* user can create manual open curve on active section plane
* user can create manual closed curve on active section plane
* manual curve appears in scene browser
* manual curve renders in viewport
* manual curve can fill/loft
* pytest passes

Stop after this task.

---

## Task 60: Curve-on-mesh snapping for manual curves

Goal:
Allow manual curve points to snap directly onto the scan mesh.

Do not add region selection.
Do not add boundary extraction.
Do not add face detection.
Do not add BREP export.
Do not implement full point editing yet.

Requirements:

1. Mesh picking API

Add a focused mesh picking method to the viewport.

Required return data:

* hit: bool
* position: np.ndarray | None
* normal: np.ndarray | None, if available
* triangle_index: int | None, if available

Preferred:

* use VTK picker/cell picker
* do not brute-force raycast in Python over millions of triangles

2. Manual curve snap mode

Add toggle:

* Snap to Mesh

Available from:

* manual curve toolbar/context
* Curves or Tools menu
* keyboard shortcut optional

When enabled:

* clicks place points on mesh hit position
* if no mesh hit, do not add point
* status: "No mesh under cursor"

When disabled:

* clicks use active work-plane placement from Task 59

3. Metadata

For a mesh-snapped manual curve:

* metadata["creation_type"] = "curve_on_mesh"
* metadata["snap_mode"] = "mesh"
* metadata["source_mesh_name"] if available

If per-point metadata is easy:

* store hit triangle indices/normals under metadata
  If not:
* leave TODO and store only curve-level metadata.

4. Visual feedback

When Snap to Mesh is ON:

* status clearly says Snap to Mesh ON
* pending points use distinct marker or line style if practical
* no heavy hover preview unless it is cheap

5. Safe behavior

Must not crash:

* with no mesh loaded
* when clicking empty background
* when mesh actor is hidden
* when point pick fails
* after deleting mesh

6. Tests

Add/update tests for:

* no hit on empty scene
* no point added when snap is on and no hit exists
* hit result structure exists
* confirmed snapped curve has curve_on_mesh metadata
* deleting mesh clears pending snapped curve mode
* snapped manual curve save/load if project supports curve metadata

Acceptance:

* app launches
* manual curve mode still works without snap
* Snap to Mesh mode places points on mesh
* no crash when clicking empty viewport
* snapped curve appears as normal curve
* snapped curve can fill/loft
* pytest passes

Stop after this task.

---

## Task 61: Mesh region selection prototype

Goal:
Add the first smart reverse-engineering selection tool: connected triangle region selection by normal angle.

Do not add automatic surface fitting.
Do not add boundary extraction yet.
Do not add patch generation.
Do not add BREP export.
Do not add dependencies.

Requirements:

1. Add region state module

Create a focused module:

* src/regions/region_state.py

Include:

* RegionSelection
* RegionCollection, if storing multiple regions
* selected triangle indices
* visible/selected flags
* source mesh identifier/name
* threshold metadata

Keep it small.

2. Add mesh adjacency module

Create:

* src/mesh/adjacency.py

Responsibilities:

* build triangle adjacency from mesh faces
* cache by mesh identity/checksum if practical
* return neighboring triangle indices

Do not build adjacency on every mouse move.
Build only when:

* mesh loaded
* first region selection requested
* mesh changes

3. Region selection mode

Add tool:

* Tools → Region Select

Behavior:

* user activates mode
* clicks mesh
* seed triangle selected
* region grows through connected triangles whose normals are within threshold of seed/region normal

Default threshold:

* 20 degrees

Maximum cap:

* 50,000 triangles default to prevent runaway selection

4. Region growing rules

Initial algorithm:

* BFS/queue over triangle adjacency
* accept neighbor if normal angle <= threshold
* stop at max triangle cap
* only connected triangles
* no curvature fitting yet

Do not attempt body-panel intelligence yet.
This is a prototype.

5. Region display

Selected region must be visible.

Minimum:

* overlay selected triangles with translucent color or highlighted wireframe
* do not duplicate/rebuild full mesh every mouse move
* update only when region selection changes

6. Region controls

Add simple controls:

* threshold value
* max triangle cap
* Clear Region Selection
* Hide Region Highlight
* Show Region Highlight

If sidebar controls are too much:

* use menu commands plus constants for first version

7. Stored or transient

Preferred:

* store one active region object in app state
* show in scene browser under Regions

Acceptable first version:

* transient active region only
* scene browser TODO

If stored:

* Regions

  * Region 1

Region should have:

* name
* triangle_indices
* threshold_degrees
* visible
* selected

8. Future TODOs

Add TODO comments for:

* add/subtract brush
* paint region selection
* boundary extraction
* convert boundary to curve
* curvature-based grow
* patch fitting from region
* auto face detection

9. Tests

Add/update tests for:

* triangle adjacency on simple quad/cube mesh
* region grow selects connected coplanar faces
* sharp normal boundary stops growth
* threshold affects region size
* max triangle cap is respected
* empty mesh returns no region
* region selection does not alter mesh geometry
* clearing region removes viewport highlight

Acceptance:

* app launches
* Region Select mode exists
* clicking mesh selects a connected region
* threshold affects result
* region highlight is visible
* existing manual curve/section/surface workflows still work
* pytest passes

Stop after this task.
