---

## Task 70: CAD Kernel / BREP Foundation — Real Surface Export Prototype

Purpose:
The current surface tools create viewport preview meshes, not actual CAD geometry. This makes region selection, boundary extraction, curve rebuilding, and surface previews feel mostly useless because the output is still just mesh-like visualization.

This task adds the first real CAD/BREP foundation.

The goal is not to make the entire app a mature CAD system yet. The goal is to prove that openRetop can convert selected prepared curves into actual CAD-kernel-backed surfaces and export them as STEP.

This is the first task where adding a CAD kernel dependency is allowed, but it must be isolated and optional.

---

## High-level goal

User workflow after this task:

1. Load scan mesh.
2. Create/edit/project/rebuild curves.
3. Select a clean closed curve or two compatible curves.
4. Create a BREP surface.
5. See it listed as a CAD/BREP surface, not just preview.
6. Export selected BREP surface to STEP.
7. Open the STEP in CAD software.

Minimum useful output:

* planar closed-curve face to STEP
* two-curve loft surface to STEP if feasible
* if loft is too risky, complete planar face export first

---

## Do not do these yet

Do not add automatic face recognition.
Do not add full solid modeling.
Do not add fillets.
Do not add trims beyond simple closed boundary if not supported by the chosen backend.
Do not add automatic region-to-solid.
Do not remove existing preview surfaces.
Do not rewrite the UI.
Do not rewrite all curve tools.
Do not integrate pboyer/verb as a runtime dependency.
Do not attempt to write a full BREP kernel from scratch.

---

## Part A — Choose and isolate CAD kernel dependency

A real BREP/STEP workflow needs a CAD kernel.

Preferred direction:

* Use an OpenCascade-based Python package if available in the environment.
* Acceptable options:

  * OCP
  * pythonocc-core
  * CadQuery only if it can expose/export the needed underlying BREP cleanly

Do not scatter CAD-kernel imports throughout the app.

Create a new isolated package:

src/cad_kernel/

Suggested files:

* src/cad_kernel/**init**.py
* src/cad_kernel/backend.py
* src/cad_kernel/types.py
* src/cad_kernel/occ_backend.py
* src/cad_kernel/export_step.py

Rules:

* Main app code must import only from cad_kernel.backend/types.
* OpenCascade/OCP/pythonocc-specific imports must live only in occ_backend.py/export_step.py.
* If the CAD dependency is missing, the app must still launch.
* BREP commands should show disabled/unavailable status instead of crashing.
* Tests that require CAD kernel should skip cleanly if backend is unavailable.

Add helper:

is_cad_kernel_available() -> bool

Add helper:

cad_kernel_status() -> str

Examples:

* "CAD kernel available: OCP"
* "CAD kernel unavailable: install OCP/pythonocc-core to enable BREP export"

Acceptance:

* App launches without CAD kernel installed.
* App exposes clear status if BREP backend is unavailable.
* No top-level import crash.

---

## Part B — Add internal CAD surface state

Current SurfacePatch only tracks metadata and source curve IDs. Add a lightweight CAD/BREP state layer without destroying existing preview surfaces.

Create or extend:

src/surfaces/brep_state.py

Dataclasses:

1. BrepSurfaceRecord

Fields:

* id: str
* name: str
* source_curve_ids: list[str]
* brep_type: str
* backend: str
* visible: bool = True
* selected: bool = False
* metadata: dict[str, object] = field(default_factory=dict)

brep_type values:

* "planar_face"
* "loft_surface"
* "unknown"

2. BrepSurfaceCollection

Fields:

* surfaces: list[BrepSurfaceRecord]
* active_surface_id: str | None
* selected_surface_ids: set[str]

Functions:

* add_brep_surface()
* remove_brep_surface()
* get_active_brep_surface()
* set_active_brep_surface()
* set_selected_brep_surfaces()
* clear_brep_surface_selection()
* get_visible_brep_surfaces()

Important:

* Do not store raw CAD kernel objects directly in the project JSON unless safely serializable.
* Store enough metadata/source IDs to rebuild/export during the session.
* For this task, session-only CAD object cache is acceptable.

Add app-state storage:

* app_state.brep_surface_collection
* optional cad runtime cache:

  * self._brep_runtime_cache: dict[str, object]

Acceptance:

* BREP surfaces are separate from preview surfaces.
* Existing preview SurfaceCollection still works.
* BREP records can be selected/deleted/listed.

---

## Part C — Add BREP backend types

Create:

src/cad_kernel/types.py

Dataclasses:

1. CadBuildResult

* success: bool
* cad_object: object | None
* reason: str
* warnings: list[str]
* metadata: dict[str, object]

2. StepExportResult

* success: bool
* path: str | None
* reason: str
* warnings: list[str]

3. CadCurveInput

* points: np.ndarray
* is_closed: bool
* name: str
* curve_id: str
* metadata: dict[str, object]

Utility:

* clean_cad_curve_points(points, closed) -> np.ndarray
* curve_points_from_stored_curve(curve) -> CadCurveInput

Rules:

* Use fitted_points for generated CAD shape unless control_points are more appropriate.
* Remove exact duplicate consecutive points.
* For closed curves, do not require duplicate final point unless backend needs it.
* Never pass NaN/inf to CAD kernel.

Acceptance:

* CAD backend receives clean curve inputs.
* Invalid curves fail with useful messages.

---

## Part D — Build planar BREP face from one closed curve

Add backend function:

build_planar_face_from_curve(curve_input: CadCurveInput) -> CadBuildResult

Input:

* one closed curve

Required validation:

* curve must be closed
* at least 3 valid points
* curve must not be degenerate
* estimate best-fit plane
* planarity error must be within tolerance

Suggested tolerance:

* model-relative where possible
* fallback absolute tolerance if no model extent available
* start with lenient warning threshold, strict failure only for clearly non-planar/degenerate curves

Build behavior:

* Convert curve points into CAD wire/edge representation.
* Build planar face from closed wire.
* Store metadata:

  * brep_type = "planar_face"
  * source_curve_id
  * source_curve_name
  * source_point_count
  * planarity_error
  * backend
  * build_method = "closed_wire_planar_face"

If CAD backend cannot make the face:

* return failure result with reason
* do not crash

Acceptance:

* simple square closed curve creates BREP face
* triangle closed curve creates BREP face
* open curve is rejected
* non-planar curve is rejected or warned depending severity
* no app crash on invalid input

---

## Part E — Build loft BREP surface from two curves

Add backend function:

build_loft_surface_from_curves(
first_curve: CadCurveInput,
second_curve: CadCurveInput,
) -> CadBuildResult

Input:

* exactly two curves

Required validation:

* both curves have at least 2 valid points
* both should be open or both closed; warn/reject mixed if backend fails
* resample/rebuild consistency should happen before this command, not inside heavy backend
* preserve curve order

Build behavior:

* Convert both curves into CAD wires/edges.
* Attempt loft surface.
* If closed curves work, support closed loft.
* If only open loft is stable, support open loft first and return clear failure for closed loft.

Metadata:

* brep_type = "loft_surface"
* source_curve_ids
* source_curve_names
* source_point_counts
* backend
* build_method = "two_curve_loft"
* warnings from validation

If loft fails:

* return failure with reason
* do not create broken BREP record

Acceptance:

* two simple parallel open curves create a loft BREP surface
* invalid pair fails clearly
* no crash on mixed open/closed curves
* metadata records source curves

---

## Part F — Add BREP creation commands

Add commands:

1. Create BREP Face From Closed Curve

Input:

* exactly one selected closed curve

Behavior:

* validates curve
* calls build_planar_face_from_curve()
* creates BrepSurfaceRecord
* stores runtime CAD object in cache
* selects BREP surface
* refreshes scene browser
* refreshes viewport if BREP preview display exists
* status:
  "Created BREP planar face from <curve name>."

2. Create BREP Loft From Two Curves

Input:

* exactly two selected curves

Behavior:

* validates curves
* calls build_loft_surface_from_curves()
* creates BrepSurfaceRecord
* stores runtime CAD object in cache
* selects BREP surface
* refreshes scene browser
* status:
  "Created BREP loft surface from 2 curves."

Failure behavior:

* show status with reason
* do not create record
* do not mark project dirty unless object was created

Undo/redo:

* created BREP surfaces should be undoable
* undo removes record and runtime object
* redo restores record and rebuilds or restores runtime object if practical
* if redo cannot restore runtime object, rebuild from source curves

Acceptance:

* BREP face command works on clean closed curve
* BREP loft command works on simple compatible curve pair
* failure states are clear
* undo/redo works

---

## Part G — STEP export for selected BREP surface

Add command:

Export Selected BREP Surface to STEP

Behavior:

* requires one selected BREP surface
* opens save-file dialog with .step / .stp
* calls export_step_selected_brep()
* writes STEP file
* status:
  "Exported STEP: <path>"
* if no BREP selected:
  "Select a BREP surface to export."
* if CAD backend unavailable:
  "CAD kernel unavailable; cannot export STEP."

Add backend helper:

export_step(cad_object, path) -> StepExportResult

Rules:

* Do not export preview mesh as STEP and pretend it is BREP.
* Only export real CAD-kernel object.
* If only mesh export is possible, fail clearly.

Acceptance:

* created planar BREP face exports to STEP
* exported file is non-empty
* invalid path fails clearly
* no crash if backend unavailable

---

## Part H — Viewport display of BREP surfaces

Minimal display is acceptable.

Option 1, preferred:

* tessellate CAD object through CAD backend or available triangulation
* convert to SurfacePreviewMesh-like display
* display in viewport with a distinct BREP color

Option 2:

* reuse existing preview mesh generated from source curves for display
* clearly label it as BREP record with preview display
* do not claim preview mesh is the exported geometry

Rules:

* BREP object is source of truth for export.
* Preview display is only visual.
* BREP surface should appear visually distinct from mesh scan and preview surfaces.

Suggested visual:

* BREP surface: muted gold or blue-green
* selected BREP: brighter cyan/gold
* wireframe overlay optional

Acceptance:

* user can see that BREP surface was created
* BREP surface does not look identical to region highlight
* selected BREP is visually identifiable

---

## Part I — Scene browser integration

Add scene browser group:

CAD / BREP Surfaces
[V] BREP Face 1 (planar face)
[V] BREP Loft 1 (loft)

Do not mix BREP surfaces under normal preview Surfaces unless clearly tagged.

If simpler:
Surfaces
Preview Surfaces
CAD / BREP Surfaces

Actions:

* Select
* Rename
* Toggle Visibility
* Hide Selected
* Show Selected
* Delete Selected
* Frame Selected
* Export STEP

Labels:

* [V] BREP Face 1 (planar face)
* [V] BREP Loft 1 (loft)

Acceptance:

* BREP surfaces are easy to distinguish from preview surfaces.
* Export STEP is discoverable from selected BREP surface.

---

## Part J — UI/workbench integration

Surfaces workbench should add a new section:

CAD / BREP Output

Controls:

* CAD Kernel Status
* Create BREP Face From Closed Curve
* Create BREP Loft From Two Curves
* Export Selected BREP Surface to STEP
* Delete Selected BREP Surface

Diagnostics:

* BREP Type
* Backend
* Source Curves
* Build Method
* Last Export Path
* Build Warnings
* Build Errors/Reason

Disabled states:

* BREP creation disabled if CAD kernel unavailable
* STEP export disabled if no BREP selected
* Loft disabled unless two curves selected
* Face disabled unless one curve selected

Do not make this top-menu-only.
It must be visible in the Surfaces workbench.

Acceptance:

* User can find BREP tools
* User can see backend availability
* User can export without guessing

---

## Part K — Project persistence

For this task, persist BREP records but not raw CAD kernel objects.

Project JSON should save:

* BrepSurfaceRecord fields
* source curve IDs
* metadata
* brep_type
* backend
* name
* visibility
* selection if existing convention supports it

On project load:

* restore BREP records
* runtime CAD object cache starts empty
* show status/metadata:
  "BREP surface record loaded; rebuild required before export."
* optional:

  * auto-rebuild BREP objects from source curves if CAD kernel available

Required command:

* Rebuild Selected BREP Surface

Behavior:

* uses metadata/source curves
* rebuilds runtime CAD object
* updates cache
* status:
  "Rebuilt BREP surface."

Acceptance:

* project save/load does not crash
* BREP records survive reload
* user can rebuild/export after reload if source curves still exist

---

## Part L — Tests

Add/update tests.

CAD kernel availability:

* app imports with no CAD kernel
* is_cad_kernel_available returns bool
* unavailable backend gives safe failure message
* BREP commands fail gracefully when backend missing

CAD types:

* clean curve points removes duplicate consecutive points
* closed curve handling does not duplicate endpoint unnecessarily
* invalid points are rejected safely

Planar face backend:

* open curve rejected
* too-few-points curve rejected
* degenerate curve rejected
* square closed curve builds if CAD backend available
* build result metadata includes brep_type/build_method

Loft backend:

* one curve rejected
* invalid pair rejected
* simple two-curve loft builds if CAD backend available
* metadata includes source curve IDs/names

Commands:

* Create BREP Face requires one selected curve
* Create BREP Loft requires two selected curves
* successful command creates BrepSurfaceRecord
* runtime cache stores CAD object
* undo removes BREP record/cache object
* redo restores or rebuilds
* delete removes BREP record/cache object

STEP export:

* export requires selected BREP surface
* export unavailable without backend
* export writes non-empty file if backend available
* failed export does not crash

Scene browser:

* CAD / BREP Surfaces group appears
* BREP surface labels include planar face/loft
* visibility toggle works
* delete works
* export action discoverable if implemented in context menu

Project persistence:

* BREP records save
* BREP records load
* raw CAD object is not serialized
* rebuild after load works if backend available

Regression:

* app launches
* mesh loading works
* manual curves still work
* region select still works
* boundary extraction still works
* projected/rebuilt curves still work
* preview surfaces still work
* existing fill/loft preview still works

Acceptance:

* pytest passes
* app launches without CAD kernel
* app uses CAD kernel if installed
* user can create at least one real BREP planar face from a clean closed curve
* user can export that BREP face as STEP
* no mesh preview is falsely labeled as BREP
* BREP tools are isolated from preview tools

## Stop after this task.
