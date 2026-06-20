---

## Task 72: ExModel-Style Manual Curves and Editable Loft Features

Purpose:
Do not continue primitive fitting yet.

The current manual curve and loft workflow is not good enough for serious reverse engineering. Manual curves should behave like CAD reverse-engineering guide curves: editable, sharp-corner aware, smooth where intended, projected/snapped to mesh when needed, and usable as persistent source geometry for editable BREP surfaces.

Generated surfaces must not be dead-end outputs. Lofted surfaces must remain editable feature objects driven by source curves and loft options. Closed lofts must support caps/end fills so the result is useful as CAD geometry, not just an open sheet.

This task is a workflow and geometry-quality overhaul for manual curves and lofts.

Do not add cylinder/cone/sphere fitting in this task.
Do not add automatic primitive classification.
Do not do UI cleanup broadly.
Do not remove existing region select.
Do not remove existing BREP planar face work.
Do not remove existing curve projection/rebuild/validation tools.
Do not add pboyer/verb yet.
Do not replace the whole application architecture.

---

## High-level target behavior

The user should be able to:

1. Create a manual curve directly on the scan mesh.
2. Mark points as sharp corners or smooth points.
3. Drag curve points and immediately see high-quality curve updates.
4. Preserve sharp corners while smoothing adjacent spans.
5. Convert a curve to a real CAD wire made of line/spline segments.
6. Select two or more curves and create an editable loft feature.
7. Edit source curves and rebuild the loft.
8. Choose whether closed lofts get start/end caps.
9. Export the resulting BREP loft/solid/shell to STEP.
10. See and edit source-curve/loft options after surface creation.

This should feel closer to ExModel:

* curves are the main modeling control
* surfaces stay tied to curves
* sharp corners do not get destroyed by smoothing
* lofts are editable features, not disposable preview meshes

---

## Part A — Replace single-method manual curves with segment-aware curves

Current curve methods are too limited:

* polyline keeps corners but is not smooth
* Catmull-Rom smooths everything and rounds sharp corners

Add a new curve model while preserving existing metadata compatibility.

Create or extend:

src/curves/manual_curve.py

Add constants:

* MANUAL_CURVE_METHOD_POLYLINE = "polyline"
* MANUAL_CURVE_METHOD_CATMULL_ROM = "catmull_rom"
* MANUAL_CURVE_METHOD_HYBRID = "hybrid"
* MANUAL_CURVE_METHOD_CAD_SPLINE = "cad_spline"

Add point type constants:

* CURVE_POINT_SMOOTH = "smooth"
* CURVE_POINT_CORNER = "corner"
* CURVE_POINT_TANGENT_LOCKED = "tangent_locked"

Add dataclass:

ManualCurvePoint

Fields:

* position: np.ndarray
* point_type: str
* tangent_in: np.ndarray | None
* tangent_out: np.ndarray | None
* weight: float = 1.0
* snap_triangle_index: int | None = None
* snap_normal: list[float] | None = None
* metadata: dict[str, object] = field(default_factory=dict)

Add dataclass:

ManualCurveControlDataV2

Fields:

* points: list[ManualCurvePoint]
* is_closed: bool
* curve_method: str
* sample_count: int
* corner_angle_threshold_degrees: float
* preserve_corners: bool
* metadata: dict[str, object]

Backward compatibility:

* Existing metadata["control_points"] must still load.
* If old control_points exist without point types:

  * infer point type from angle:

    * sharp angle below threshold -> corner
    * otherwise smooth
  * preserve old curve_method
* Existing curves should not break.

Acceptance:

* Existing manual curves still load.
* New curves store per-point point_type.
* Old curves can be upgraded to V2 metadata without data loss.
* Project save/load preserves point types.

---

## Part B — Add sharp-corner-aware curve sampling

Add new sampling function:

sample_hybrid_manual_curve(
control_data: ManualCurveControlDataV2,
) -> np.ndarray

Behavior:

* Split curve into smooth spans separated by corner points.
* Smooth spans should use a stable spline/Catmull/B-spline-like interpolation.
* Corner points must be exact pass-through points.
* No smoothing should overshoot through a corner.
* Open curves must preserve endpoints.
* Closed curves must preserve closure.
* For two-point spans, use line segment sampling.
* For corner-to-corner segment with no smooth interior points, use line segment.
* For smooth runs, use smooth interpolation.

Rules:

* Sharp corners are hard constraints.
* Smooth sections can be smoothed.
* Smoothing must not move control points.
* Sampling must be deterministic.
* No NaN/inf output.

Add curve quality diagnostics:

* point_count
* control_point_count
* corner_count
* smooth_span_count
* max_corner_angle
* min_segment_length
* endpoint_gap
* closed/open
* overshoot_warning if sampled curve leaves local control polygon too aggressively

Acceptance:

* A square curve with all corner points remains square.
* A curve with smooth intermediate points becomes smooth only between corners.
* A curve with mixed smooth/corner points behaves predictably.
* Closed hybrid curve closes cleanly.
* Open hybrid curve preserves endpoints.

---

## Part C — Add point-type editing tools

Manual Curve Edit mode needs explicit point-type controls.

Add UI/commands:

* Set Selected Point Smooth
* Set Selected Point Corner
* Toggle Selected Point Smooth/Corner
* Auto Detect Corners
* Smooth Selected Span
* Straighten Selected Span

Behavior:

* selecting a point shows its type
* point markers should visually distinguish:

  * smooth point: white/blue small sphere
  * corner point: square/cube marker or different color
  * selected point: highlighted
* Auto Detect Corners:

  * uses local angle threshold
  * default threshold: 135 degrees interior angle or equivalent deflection threshold
  * updates point types only, not positions
* Smooth Selected Span:

  * works only between nearest corner endpoints
  * does not move corner points
* Straighten Selected Span:

  * converts selected span to polyline/line-like segment
  * preserves endpoints

Acceptance:

* user can manually mark sharp corners
* smoothing no longer ruins corners
* point types survive save/load
* viewport updates immediately

---

## Part D — Improve curve creation workflow on mesh

Manual curve creation should be fast and predictable.

Add creation options:

1. Curve Mode:

* Smooth
* Polyline
* Hybrid

2. Point Placement:

* Snap to Mesh
* Work Plane
* Free 3D

3. Corner Behavior:

* Auto corner detection ON/OFF
* Preserve sharp corners ON/OFF

4. Closure:

* Close Curve
* Auto-close when clicking first point
* Show closure preview

Workflow:

* User clicks points on mesh.
* Each new point gets inferred point type:

  * if Auto corner detection OFF: use current default point type
  * if ON: update previous point type based on angle after new point is added
* User can press hotkey or button to toggle next point between Smooth/Corner.
* Existing ghost preview remains.
* Closed curve preview should show whether closure will be smooth or corner.

Suggested shortcuts:

* C = next/selected point corner
* S = next/selected point smooth
* Enter = finish curve
* Esc = cancel
* Backspace = remove last point

Acceptance:

* curve creation is not slower than current workflow
* clicking around a square can create a square with sharp corners
* clicking around a smooth fender contour can create a smooth curve
* user can mix smooth and sharp points in one curve

---

## Part E — CAD wire generation from hybrid curves

Create new module:

src/cad_kernel/curve_wire.py

Purpose:
Convert editable manual curves into CAD wires without destroying sharp corners.

Add function:

build_cad_wire_from_curve(curve: StoredCurve) -> CadBuildResult

Behavior:

* parse V2 manual curve metadata if available
* if curve has corner/smooth segments:

  * corner-to-corner straight spans become CAD line edges where appropriate
  * smooth spans become CAD spline edges
  * join all edges into one CAD wire
* if old curve:

  * use current fitted points as fallback
* preserve closed/open state
* return useful failure reason if wire cannot be built

For CadQuery:

* use Wire.makePolygon for polyline/corner-only curves
* use spline/wire APIs where possible for smooth spans
* if CadQuery spline wire support is limited, use OCP APIs directly if available
* keep all backend-specific code isolated in cad_kernel

Important:

* Do not sample everything into hundreds of line segments unless the backend cannot make spline edges.
* Prefer real spline/line edge topology.
* Sharp corners should become actual topological vertices between edges.

Metadata:

* cad_wire_edge_count
* cad_wire_line_edge_count
* cad_wire_spline_edge_count
* cad_wire_closed
* cad_wire_build_method
* cad_point_source

Acceptance:

* hybrid square curve becomes four CAD line edges
* smooth curve becomes spline wire
* mixed curve becomes line/spline wire
* wire can be used for planar face and loft creation
* failure messages are clear

---

## Part F — Replace BREP face/loft curve conversion with CAD wires

Update existing BREP face and loft builders to use CAD wire generation where possible.

Planar face:

* selected closed hybrid curve
* build CAD wire
* make face from wire
* preserve corners exactly

Loft:

* selected source curves
* build CAD wires from each source curve
* loft through wires
* preserve sharp corners by matching edge/topology where possible

Fallback:

* if V2 wire build fails, use existing point-based build path
* status should show fallback:
  "Used sampled curve fallback; inspect sharp corners."

Acceptance:

* square closed curve creates planar BREP face with sharp CAD corners
* smooth closed curve creates smooth face boundary
* mixed curve creates mixed line/spline boundary
* existing old curves still work

---

## Part G — Add editable loft feature records

Current generated surfaces must become editable features.

Create or extend:

src/surfaces/loft_feature.py

Dataclass:

LoftFeatureOptions

Fields:

* source_curve_ids: list[str]
* source_order_locked: bool = True
* use_cad_wires: bool = True
* match_curve_directions: bool = True
* align_closed_curve_seams: bool = True
* preserve_corners: bool = True
* cap_start: bool = False
* cap_end: bool = False
* create_solid_if_closed: bool = False
* ruled: bool = False
* smoothing: str = "normal"
* rebuild_on_source_edit: bool = True
* metadata: dict[str, object] = field(default_factory=dict)

Dataclass:

LoftFeatureRecord

Fields:

* id: str
* name: str
* options: LoftFeatureOptions
* brep_surface_id: str | None
* preview_surface_id: str | None
* last_build_success: bool
* last_build_reason: str
* last_build_warnings: list[str]
* metadata: dict[str, object]

Purpose:

* source curves are the editable definition
* BREP object is the generated result
* editing curves should allow loft rebuild
* options can be changed after creation

Acceptance:

* loft feature records persist
* source curves remain editable
* BREP loft can be rebuilt from feature options

---

## Part H — Add ExModel-style loft command

Add command:

Create Editable BREP Loft From Curves

This should replace the practical use of the older simple loft, but do not delete old loft yet.

Workflow:

1. User selects two or more curves.
2. Command creates LoftFeatureRecord.
3. CAD wires are built from source curves.
4. CAD loft is built from wires.
5. BREP record is created and linked to loft feature.
6. User can select loft feature/surface.
7. User can edit source curves.
8. User can click Rebuild Loft.

Required source counts:

* minimum: 2 curves
* more than 2 curves allowed if backend supports multi-section loft
* if backend only supports 2 curves currently:

  * support 2 first
  * fail clearly for >2:
    "Multi-section editable loft not implemented yet."

Options UI:

* Preserve Corners
* Match Directions
* Align Closed Seams
* Cap Start
* Cap End
* Create Solid if Closed
* Ruled / Smooth
* Rebuild on Source Edit

Acceptance:

* two closed profiles create editable loft feature
* two open guide curves create editable sheet
* sharp corners remain visible in loft if source curves have corners
* source curve edits can rebuild loft
* feature stores source curve IDs and options
* STEP export uses rebuilt BREP object

---

## Part I — Fill/cap loft edges

User complaint:
"Generated surfaces can't be edited, and it also doesn't fill the edges of lofted surfaces."

Implement cap options for lofts.

Definitions:

* For loft between closed section curves:

  * cap_start creates a planar/end face at first profile
  * cap_end creates a planar/end face at last profile
  * create_solid_if_closed attempts to sew shell into solid if possible
* For loft between open curves:

  * do not invent caps unless user supplies boundary rails
  * show clear message:
    "Open curve loft creates an open sheet. Use four-boundary patch or add rails to close sides."
* For four boundary curves:

  * generate a bounded surface patch instead of a simple loft

Implementation:

* closed profile loft:

  * build loft shell/surface
  * build planar faces from first/last closed wires if cap options enabled
  * sew/join shell if backend supports it
  * if sewing fails, keep separate BREP faces but group under one loft feature
* if CadQuery supports making a solid from loft:

  * use that where stable
* if not:

  * create shell or compound with explicit metadata:
    "closed_loft_with_caps_compound"

Acceptance:

* closed loft can produce capped ends
* STEP export includes caps if created
* UI clearly distinguishes open sheet vs capped/solid result
* no false claim that open loft is closed

---

## Part J — Editable surface/loft rebuild UI

Add a new panel/section in Surfaces workbench:

Editable Loft Feature

Shown when selected BREP surface has a linked LoftFeatureRecord.

Fields:

* Loft Name
* Source Curves
* Curve Count
* Preserve Corners
* Match Directions
* Align Closed Seams
* Cap Start
* Cap End
* Create Solid if Closed
* Ruled/Smooth
* Last Build Status
* Last Build Warnings

Buttons:

* Rebuild Loft
* Select Source Curves
* Edit Source Curve
* Reverse Selected Source Curve Direction
* Move Source Curve Up
* Move Source Curve Down
* Duplicate Loft Feature
* Delete Loft Feature

Do not over-polish layout.
Make functionality accessible.

Acceptance:

* user can select loft and see how it was made
* user can change options and rebuild
* user can reorder curves if loft twists
* user can reverse curve direction without recreating everything

---

## Part K — Source curve edit invalidation/rebuild

When a source curve used by a loft feature is edited:

* mark linked loft feature dirty
* show status:
  "Loft source curve changed; rebuild loft."
* if rebuild_on_source_edit=True:

  * rebuild automatically after edit completes, not during every mouse move
* do not rebuild continuously while dragging unless performance is acceptable

Metadata:

* loft_feature_dirty = True/False
* source_curve_revision numbers if available
* last_rebuild_time/session counter if available

Acceptance:

* editing a source curve does not leave loft silently stale
* user can rebuild loft after editing
* auto-rebuild happens only at safe times

---

## Part L — Region boundary curves should use hybrid corner detection

Region boundary extraction currently creates dense boundary curves.

Update extraction-to-curve behavior:

* boundary curves should be convertible to Hybrid Curve V2
* Auto Detect Corners should identify sharp changes in boundary direction
* user should be able to simplify/rebuild while preserving corner points
* region boundary curves should be editable like manual curves

Add command:

* Convert Boundary to Hybrid Guide Curve

Behavior:

* takes selected region boundary curve
* detects corners
* creates cleaner hybrid manual curve
* selects new guide curve
* original boundary remains unchanged

Acceptance:

* extracted rectangular/box-like boundary becomes hybrid curve with corners
* smooth organic boundary remains mostly smooth
* converted guide curve can drive BREP face/loft

---

## Part M — Improve four-boundary patch as editable feature

Add feature record similar to loft:

FourBoundaryPatchFeatureRecord

Fields:

* source_curve_ids: list[str]
* preserve_corners: bool
* match_directions: bool
* fill_method: str
* brep_surface_id: str | None
* last_build_status
* metadata

Goal:

* four curves define a patch
* source curves can be edited
* patch can be rebuilt

This does not need to be perfect NURBS yet.
But it should be feature-driven, not dead preview mesh.

Acceptance:

* four-boundary patch can be selected and rebuilt
* source curve edits mark patch dirty
* patch options persist

---

## Part N — Tests

Add/update tests:

Manual curve V2:

* old control_points metadata still loads
* V2 point types save/load
* corner points preserve exact position
* square hybrid curve samples with sharp corners
* smooth-only curve remains smooth
* mixed curve has both line-like and smooth spans
* closed hybrid curve closes cleanly
* open hybrid curve preserves endpoints

Corner detection:

* square detects four corners
* smooth arc detects no false sharp corners
* noisy line does not create excessive corners
* threshold changes result predictably

CAD wire:

* corner-only square builds CAD wire with line edges if backend available
* smooth curve builds spline wire if backend available
* mixed curve builds line/spline wire if backend supports it
* fallback path works without crashing
* wire metadata counts edges

BREP face:

* square hybrid curve creates BREP planar face with sharp corners
* smooth closed curve creates valid BREP face
* old curve still creates BREP face

Editable loft:

* create loft feature from two curves
* loft stores source curve IDs
* loft stores options
* rebuild loft works
* source curve edit marks loft dirty
* source curve edit can auto-rebuild on edit completion
* curve direction reversal changes/rebuilds loft
* source curve reorder changes/rebuilds loft
* closed profile loft can create cap_start
* closed profile loft can create cap_end
* open loft warns that side edges remain open
* STEP export includes rebuilt BREP object

Region boundary conversion:

* boundary curve converts to hybrid guide curve
* detected corners preserved
* original boundary unchanged
* converted guide curve can drive BREP face

Four-boundary feature:

* stores source curves
* rebuilds from source curves
* marks dirty when source curve edited
* preserves options

Regression:

* app launches
* old manual curves still work
* manual curve creation still works
* region select still works
* region-to-planar-BREP still works
* BREP export still works
* preview surfaces still work
* existing project files load
* app launches without CAD kernel

Acceptance:

* pytest passes
* app launches
* manual curves can preserve sharp corners and smooth spans
* BREP face/loft generation uses source curve topology where possible
* lofts are editable/rebuildable features
* closed lofts can be capped
* open lofts clearly remain open unless rails/boundaries are supplied
* region boundaries can become clean hybrid guide curves
* no primitive cylinder/cone/sphere work in this task

## Stop after this task.
