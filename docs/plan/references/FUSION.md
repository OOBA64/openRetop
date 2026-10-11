# Fusion sketching and solid modelling: reference for openRetop

This is what Autodesk Fusion does in its flagship CAD features: sketching, the constraint
solver, AutoConstrain, solid features, history and parameters, and the mesh-to-CAD tools.
It is written so an openRetop coding session can build the same behaviour without guessing.

- **Source.** Fusion (Personal), install build `736d2b4c…`, Windows, at
  `%LOCALAPPDATA%\Autodesk\webdeploy\production\736d2b4c5e6b95e77c11721da222cf21c6a1fc1f`.
  Collected 2026-10-11.
- **How.**
  - The shipped Python API stubs (`API/Python/packages/adsk/defs/adsk/fusion.py`, 66k lines).
  - Fusion's own automation schemas (`Fusion/Server/Fusion/Resources/MCP/Schema/*.json`) and the
    AutoConstrain report schemas (`…/Resources/Schema/*.json`).
  - The en-US UI string tables (`StringTable/en-US/*.xml`, 38,759 labels and tooltips).
  - String inventories of `NaSketch10.dll`, `VCS.dll` and `NsAutoDimensionEngine10.dll`.
  - A short live session in the running app, in a new unsaved design: sketch palette,
    rectangle tool, constraint colouring, Extrude and Fillet dialogs.
- **Use it as a behaviour spec.** No Autodesk code is copied. The appendices are condensed
  digests of the public API (signatures, enum values, one-line summaries).
- **Confidence tags.** **[O]** observed (in the files or on screen). **[D]** derived from
  several observations. **[I]** inferred; check it before relying on it.

Appendices, which a coding session should grep rather than read end to end:
- [fusion/api_sketch.md](fusion/api_sketch.md): every sketch entity, constraint, dimension,
  profile and sketch method (about 1,300 lines).
- [fusion/api_features.md](fusion/api_features.md): every solid and surface feature input,
  extent type, enum, timeline, parameter and construction-geometry class (about 3,000 lines).

---

## 0. Architecture at a glance [O]

| Layer | Binary or file | Notes |
|---|---|---|
| B-rep kernel | `ASM*232.dll` (Autodesk ShapeManager, 41 modules: BOOL, BLND (fillets), OFST, SHL (shell), SWP (sweep), SKIN (loft), COVR (patch), HEAL, …) | The equivalent of openRetop's OCC/CadQuery |
| Sketch | `Applications/DirectModeling/NaSketch10.dll` | Sketch entities, profiles, Fit Curves to Mesh Section, offset solver |
| 2D constraint solver | `VCS.dll` (Autodesk **Variational Constraint Solver**) | See §2 |
| AutoConstrain | `NsAutoDimensionEngine10.dll` ("ADE") plus a cloud ML service | See §3 |
| Features and timeline | `Applications/Fusion/NaFusion10.dll` (52 MB) | Parametric features, history, parameters |
| Mesh-to-CAD | `NaParaMesh*` | See §6 |
| Freeform | `tsplines14.dll` | T-Splines "Form" environment (out of scope here) |

- **Internal units are centimetres and radians.** Every API length is in cm, and the MCP schema
  says "numbers in cm". The UI shows document units (this design: mm) [O].
- Commands live in the timeline as features. Each has a **health state**: Healthy,
  Warning, Error, Suppressed, RolledBack or Unknown (`FeatureHealthStates`), plus an
  `errorOrWarningMessage` [O].

---

## 1. The sketch environment

### 1.1 Sketch Palette (on screen, with defaults) [O]
Seen when the sketch opened:

| Option | Default | Meaning |
|---|---|---|
| Linetype | two toggles | Construction and Centerline, applied to selected curves or to new ones |
| Look At | button | Turns the view square to the sketch plane |
| Sketch Grid | on | |
| Snap | on | Snap to the grid |
| Slice | off | Cuts away bodies in front of the sketch plane, so the plane can be seen inside a part |
| Profile | on | Fills closed regions (light shading) |
| Points | on | |
| Dimensions | on | |
| Constraints | on | Constraint glyphs next to the geometry |
| Projected Geometries | on | |
| Construction Geometries | on | |
| 3D Sketch | on (this install) | Allows sketching off the plane. Greyed out while a drawing tool is active |

While a tool runs, the palette gains a **Feature Options** section, for example Rectangle:
2-point / 3-point / centre, and construction [O].

### 1.2 Drawing behaviour seen live [O]
- **Heads-up value fields.**
  - The rectangle tool shows editable width and height fields next to the cursor; Tab moves
    between them.
  - Typed values become **driving dimensions** on the result (40.00 and 25.00 appeared as
    dimensions).
  - The first active field was the *vertical* one in this case (the order follows the drag
    direction [I]).
- **Constraints inferred automatically.**
  - A rectangle is created with horizontal and vertical constraints (glyphs on all four sides).
  - While dragging with near-equal sides (53.486 × 53.486), a **blue square glyph** appeared,
    which looks like an equal-sides inference.
  - Inference is shown as a glyph while drawing, then becomes a real constraint on click.
- **Colours.**
  - Under-defined curves are **blue**.
  - After dragging the free corner onto the origin, which made a coincident constraint, the
    sketch became fully defined and the lines turned **white** (dark theme; black in light
    theme).
  - Closed regions are shaded as **profiles**.
  - The sketch's browser entry shows its constraint state.
- **Status bar.** Selecting a profile in Extrude showed "1 Profile | Area : 1000.00 mm^2".
  Fusion reports the area of selected profiles.

### 1.3 Sketch entities and tools (API) [O]
Full signatures are in [api_sketch.md](fusion/api_sketch.md).

- **Points** and **lines**: two points; by midpoint.
- **Rectangles**: 2-point, 3-point (rotated), centre-point.
- **Polygons**: inscribed or circumscribed (`addScribedPolygon`), by edge (`addEdgePolygon`).
  Plus a **Polygon constraint** that keeps a regular polygon regular.
- **Circles**: centre-radius, 2-point, 3-point, tangent to two lines plus radius, tangent to
  three lines.
- **Arcs**: 3-point, centre-start-sweep, centre-start-end, and **fillet** between two curves
  (trims them).
- **Slots**: centre-to-centre, overall, centre-point, 3-point arc slot, centre-point arc slot.
- **Ellipse and elliptical arc**. **Conic** (start, end, apex, `rho`).
- **Fitted spline** (through points; `addBlendCurve` with G1 or G2 between two curves).
  **Control-point spline** (degree 3 or 5).
- **Sketch chamfer**: distance-distance or distance-angle.
- **Text**, including text on a path.
- **Editing**:
  - `SketchCurve.split/trim/breakCurve/extend(point, createConstraints=True)`. Edits keep
    constraints by default.
  - `Sketch.mirror(entities, line)`.
  - `move/copy/scale`.
  - **Offset** (`createOffsetInput` → `addOffset2`, two-sided with linked distances). Offset
    is a constraint, so it updates when the original changes.
- **Reference geometry**:
  - `project2(entities, isLinked)`: projected edges stay **linked** and update with the model.
  - `include`.
  - `intersectWithSketchPlane`.
  - `projectCutEdges(body)`.
  - `projectToSurface`.
  - Mesh sections (§6).
- **Linetype states**: `setConstructionState`, `setCenterlineState`.
  - **Centerlines** matter: a dimension from a centerline to a point becomes a **linear
    diameter** dimension (`addLinearDiameterDimension`). Revolve uses this.
- **Spun profile**: the turned silhouette of a body about an axis, as sketch curves.

### 1.4 Geometric constraints (API, complete list) [O]
- Point–curve or point–point: **Coincident**, **MidPoint**.
- Lines: **Horizontal**, **Vertical** (on lines), **HorizontalPoints** and **VerticalPoints**
  (on two points), **Parallel**, **Perpendicular** (and `addPerpendicular2(line, curve)`, which
  is normal to a curve), **Collinear**.
- Curves: **Tangent**, **Smooth** (G2), **Equal**, **Concentric**,
  **Symmetry** (two entities about a line).
- Patterns and groups: **RectangularPattern** and **CircularPattern**, which are *constraints*
  in the sketch, not features. **Offset**, **Polygon**.
- Fix: `SketchEntity.isFixed`.
- To 3D geometry: **CoincidentToSurface**, **LineParallelToPlanarSurface**,
  **LineOnPlanarSurface**, **PerpendicularToSurface**.

Each constraint has a selection id and a localized name in `NaSketch10.xml`, which lists the
same set plus Fixed and Smooth.

Error strings worth reusing [O]:
- "Constraint has already been applied to the selected sketch object."
- "Please delete or modify one of the following constraints/dimensions" (shown on an
  over-constraint, with the conflicting items listed).
- "Cannot change the dimension of a fixed geometry".
- "Cannot apply Polygon constraint. The geometry you selected is not a regular polygon …".
- "Failed to generate profile as, curves do not precisely overlap." (profile build).

### 1.5 Dimensions (API) [O]
- **Distance**: Aligned, Horizontal or Vertical orientation.
- **Offset** (line to entity), **Angular**, **Radial**, **Diameter**.
- **Ellipse** major and minor radius.
- **Concentric-circle** distance.
- **Tangent-distance** (to the near or far side of a circle).
- **Linear-diameter** (centerline to point; used for revolve profiles).
- Point-to-surface and line-to-planar-surface.

Every dimension has:
- `isDriving`. Driven dimensions are reference-only.
- `value`.
- `parameter`, a **ModelParameter**. Every driving dimension *is* a named parameter (`d1`, `d2`,
  …) whose `expression` may reference other parameters.

### 1.6 Profiles [O]
- Profiles are computed from closed loops automatically (`Sketch.profiles`, each made of
  `ProfileLoop`s and `ProfileCurve`s).
- The API offers `Profile.areaProperties()`.
- Open profiles for surface features come from `Component.createOpenProfile` and
  `createBRepEdgeProfile`.
- Overlapping closed curves split into several selectable regions. The Extrude command can take
  any subset, plus planar faces, as long as they are coplanar.

### 1.7 openRetop mapping
`modeling/sketch2d.py` already has points, lines, circles and arcs. It has 12 geometric kinds
(coincident, horizontal, vertical, parallel, perpendicular, tangent, equal, concentric,
midpoint, symmetric, collinear, fix) and distance, angle, radius and diameter dimensions. It has
an LM minimum-norm solver, DOF from the Jacobian rank, and "fully defined" from the null space.
That matches Fusion's model well. Gaps, highest value first:
1. **Dimensions as named parameters with expressions** (d1 = d2*2, user parameters). See §5.
2. **Heads-up value entry** while drawing (Tab between fields, typed values become driving
   dimensions), and **inference glyphs**: H/V when near-axis, coincident on hover, equal for
   a near-square rectangle, tangent at arc ends.
3. **Linked projection** of model edges and the scan section (§6) into the sketch, plus
   **Offset** as a constraint.
4. **Slots, polygons with a polygon constraint, sketch fillet and chamfer that trim**, and
   **trim/extend that keep constraints** (`createConstraints=True`).
5. **Sketch patterns as constraints**, **Smooth (G2)**, ellipses and splines.
6. The over-constraint UX: name the conflicting items and ask the user to delete one.

---

## 2. The constraint solver (VCS) [O strings, D/I behaviour]

`VCS.dll` exports a rigid-body constraint solver (the same family as Inventor and AutoCAD):
- **Model.** Each sketch entity is a `VCSRigidBody` with degrees of freedom. There are
  `removeTranslationFreedom`, `removeRotationFreedom`, `restoreDOF`, `setGrounded` and
  `GroupOfBodies`. Constraints are `ConHandles` between one or two bodies (`Ext1BodySolver`,
  `Ext2BodySolver`), and parametric dependencies are tracked per body.
- **Solve cascade**, from the success counters it logs:
  1. "Pre-positioning solve"
  2. **MergeSetSolve**: rigid clusters are merged and solved as units (graph decomposition)
  3. **PhaseTwoSolve**
  4. **NumericalSolve**: a general Newton-type fallback (`VCSEquationSystem`,
     `VCSLinearEquationSystem`)
  5. **SafeguardSolve**: the last resort
  6. **TrialSolve**, used to test a candidate constraint without committing it

  It also records "UnsolvedBodyRatioLessThanPercent20/40/60/80" statistics.
- **Diagnostics**: `RedundantChecking`, `VCS_AnalyzeInConsistent` (it finds the conflicting set
  for the "delete one of the following" message), `Rigidity` tests (`ExtRigidTester`,
  `isExtProfRigid`).
- **Drag**: `VCS_Drag`, `kDragging`, `kDragLock`, `solveForDragBegin`. Drag is a separate mode
  that locks the dragged entity and solves the rest. `kNeedDOF` and
  `kNoDOFRemovalForMinCons` are internal flags.
- Sketch-side callers in NaSketch: `SketchConstraintSolver`, `SolverPreprocessor`,
  `OffsetSolver` (a separate solver for offset constraints), `solveNewAddedConstraint`,
  `sketch_trial_solve`, and `onPreSketchSolve`/`onPostSketchSolve` hooks.

**For openRetop** [I]:
- Keep the LM solver; it is the right "numerical" stage.
- Add two cheap layers in front, as VCS does:
  - (a) **Decomposition**: solve connected components of the constraint graph separately, and
    collapse rigidly fixed clusters first. This speeds up large sketches and stops unrelated
    geometry from moving.
  - (b) **Trial solve before committing a new constraint**. If it fails, or moves fixed or
    fully defined geometry, reject it with the conflicting set. Find that set by removing
    constraints one at a time, or from the rank of J restricted to the new row.
- Keep a dedicated drag path: openRetop's `drag()` freezes the dragged point, which matches
  `kDragLock`.

---

## 3. AutoConstrain (fully constrain a sketch in one click) [O]

UI: "AutoConstrain" and "AutoConstrain from datum".
- Progress messages: "Analyzing sketch…", "Constraining sketch…", "Adding constraints and
  dimensions…".
- The user picks from **3 alternatives** (`AutoConstrainResultTypes` Option1..3).
- The tip calls it "AI technology".
- The API is `Sketch.autoConstrain(input)`, which returns `isFullyConstrained`.

How it works, from `AutoConstrainReport.json` and the engine's algorithm names:
1. **Inputs.**
   - The sketch's entity counts and under-constrained status per type.
   - **Loops** (closed chains with their points, curves and a `loop_datum`).
   - A **datum**: the origin, or a user-picked "Datum Selection" reference for "from datum".
2. **Recipes.**
   - The heuristic engine (ADE) generates several recipes. The UI calls them "result tiles".
   - Optionally a cloud **ML** recipe is added (`ais-constraingen` endpoint, model hash and
     version recorded).
   - Each recipe is a list of proposed constraints and dimensions, each with a
     `dimension_priority`, an algorithm `footprint`, and a `zone`.
3. **Generators** (names in the engine):
   - `Horizontal/VerticalBaseLineDimGenAlgorithm` (baseline dimensioning from a datum).
   - `Horizontal/VerticalChainDimGenAlgorithm` (chain dimensioning).
   - `SymmetricDimsGenerator`, `SymmetricWithBaselineDimsGenerator`,
     `SymmetricWithOrdinateDimGenAlgorithm`.
   - `ConcentricCirclesDimensionGeneratorAlgo`.
   - `DatumToFixedPointDimGenAlgo`, `ViewDatumToLoopDatumDimGenAlgo`.
   - `EqualConstraintGeneratorAlgo`, `PerpendicularConstraintGeneratorAlgo`.
   - Shape recognisers: `CenterRectangle`, `TwoPointRectangle`, `ThreePointRectangle`,
     `MidpointLinearSlot`, "Center-To-End-With-Symmetry".
   - Options: `preferSymmetricDims`, `preferHoleAndThreadNoteOverDimension`,
     `maxNumberOfConstraintsAndDimensionsToBeGenerated`.
4. **Priority modifiers**, which rank the candidates:
   - Rectangular-loop boosts (perpendicular, offset and angular dimensions in rectangles).
   - Arc–arc, circle–arc and circle–circle priorities, and diametric for circles.
   - `HighPriorityAngularDimIdentifierAlgo`.
   - `SmallDimPriorityModifierAlgo`.
   - `TangencyPointPriorityAlgo`.
   - `ThreeEdgesIntersectionDimPriorityAlgo`.
   - `UniqueSectionPriorityReducingAlgo`.
   - "Offset dimension preferred over linear" (`PriorityChangeFactorForOffsetDimOverLinearDim`).
5. **Clean-up**:
   - `RedundantDimensionRemovalAlgorithm`.
   - `AngularDimensionsWithSameMeasuringAngleMergingAlgo`.
   - `DimensionRegionBasedFilterAlgorithm`.
   - "Fungible" handling: interchangeable dimensions, any one of which removes the same DOF.
6. **Zones.**
   - **Green**: applied.
   - **Yellow**: plausible but demoted, for example chamfer dimensions, dimensions with no
     common edge, or radial dimensions on small arcs ("MoveToYelloZone").
   - **Red**: would conflict, or the user deleted it before ("MoveUserDeletedConstraintsToRedZone").
7. **Apply with a solve check.**
   - Each item is test-solved in VCS. A **background solve timeout** exists.
   - Items are skipped "because geometries were fully constrained".
   - Each result is graded with `quality_metrics`: fully constrained? did geometry move? could
     it have moved? how many over-constraining items?
8. **Geometry fixer.**
   - Optionally ("modify geometry") snaps near-relations within user
     **LinearTolerance/AngularTolerance** settings before constraining.
   - Shows applied, failed and red-zoned items.

**For openRetop.** This is the right model for constraining the auto-fitted section sketches
(S-13). The fitter already produces lines and arcs; a heuristic AutoConstrain then:
1. Snaps near-H/V lines and near-tangent joins (geometry fixer, with a tolerance).
2. Adds coincident, tangent, equal and concentric constraints.
3. Dimensions from a datum: the scan's aligned origin, using baseline for prismatic parts and
   symmetric about a centerline for turned parts.
4. Ranks the candidates and discards redundant ones by **trial-solving each candidate and
   keeping it only if the DOF drops and nothing moves**.
5. Offers 2–3 alternatives (baseline, chain, symmetric).

No ML is needed for a first version.

---

## 4. Solid features

Defaults come from the live dialogs [O] and the automation schema [O]. Full inputs are in
[api_features.md](fusion/api_features.md). Common to every body feature: `operation` is
**Join, Cut, Intersect, New Body or New Component**, and `participantBodies` limits which
bodies a Cut, Join or Intersect touches.

### 4.1 Extrude
Live dialog defaults [O]:

| Input | Default | Choices |
|---|---|---|
| Type | Solid | Solid or **Thin** |
| Profiles | auto-selects when the sketch has exactly one profile | Coplanar profiles and/or planar faces |
| Start | Profile Plane | **Profile Plane**, **Offset** (distance), **Object** (face or plane) |
| Direction | One Side | **One Side**, **Two Sides**, **Symmetric** |
| Extent Type | Distance | **Distance**, **To Object** (with `isChained`, `isMinimumSolution` near/far side, offset), **All** (through all) |
| Distance | 0.00 mm (typed or dragged on the arrow) | Expression |
| Taper Angle | 0.0 deg (separate per side for Two Sides) | |
| Operation | New Body for the first body; later extrudes suggest Join or Cut by direction [I] | |

More details:
- **Symmetric** has `isFullLength`. The default, false, measures **per side** [O].
- **Thin**:
  - wall location **Side1, Center or Side2**, default **Center** [O];
  - a thickness per side;
  - works on open profiles.
- Manipulators [O]: a distance arrow and a taper-angle handle on the profile, plus a floating
  value box.
- **openRetop**: `cad_kernel/features.py` has extrude with low/high, draft and
  combine(mode). The missing pieces are To Object (including "up to the scan", which is
  openRetop-specific), Through All, Start Offset/Object, Thin, the per-side taper, and
  participant bodies.

### 4.2 Revolve [O schema]
- Profiles plus an **axis** (construction axis, sketch line, linear edge, or X/Y/Z).
- Extent: **angle**, **full**, or **toEntity**.
- Direction: one side, two sides (`angleTwo`), or symmetric.
- `isSolid` defaults to true; false makes a surface.
- Same operations as Extrude.

### 4.3 Sweep, Loft, Rib, Web, Pipe, Coil [O API]
- **Sweep**: profile(s) along a path. Options:
  - Orientation: Perpendicular, Parallel.
  - Profile scaling: Scale, Stretch, None.
  - Optional **guide rail** or **centerline**.
  - Distance, taper and twist angle along the path.
  - Extent: PerpendicularToPath or FullExtents.
  - Solid-body sweep: Perpendicular, Rigid or Aligned.
- **Loft**: ordered sections, with end conditions per section: Free, Direction (angle + weight),
  Tangent (weight), Smooth (G2), PointSharp, PointTangent.
  - Rails or a centerline; rail edge conditions G0/G1/G2.
  - Edge alignment: Free, Align edges, Align to surface.
  - `isClosed`, `isTangentEdgesMerged`.
- **Rib** and **Web**: thickened open sketch curves up to the body.
- **Pipe**: circular, square or triangular section along a path; hollow thickness.
- **Coil**: revolutions + height, revolutions + pitch, height + pitch, or spiral. Default
  **5 turns**.

### 4.4 Fillet [O live + schema]
- Dialog defaults:
  - Type **Fillet**. The alternatives are **Rule Fillet** (by rule: all edges, between faces or
    features) and **Full Round** (three faces).
  - A **list of selection sets**, each a row with its own radius type and values (+/− to add
    and remove rows).
  - Radius Type: **Constant**, **Chord Length** or **Variable** (start/end and mid-point radii
    along the edge).
  - **Tangent Chain** on.
  - Continuity per row **Tangent (G1)**, or **Curvature (G2)** with **Tangency Weight 1.00**
    (range 0.1–2.0).
  - Corner Type **Rolling Ball**, or **Setback**.
- Selecting a **face** selects all its edges ("1 Face" row) [O].
- The radius starts at 0.00 mm and is dragged with an on-canvas arrow [O].
- The automation schema adds asymmetric (two offsets, `isFlipped`) and face fillets [O].

### 4.5 Chamfer [O API]
- Edge sets, each one of: **Equal Distance**, **Two Distances**, **Distance and Angle**.
- Tangent chain.
- Corner type: **Chamfer**, **Miter** or **Blend**.

### 4.6 Shell, Draft, Scale, Combine, Split, Mirror, Patterns
- **Shell** [O]:
  - Pick faces to remove; thickness inside or outside.
  - **Closed shell** (hollow body) when a body is picked; open when faces are picked.
  - Shell type: Sharp or Rounded offset.
  - Tangent chain.
- **Draft** [O]:
  - **Fixed Plane** or **Parting Line**; angle; flip; symmetric or two-sided.
  - The tip says the parting line can be "a plane, face, edge, or sketch curve".
- **Scale**: uniform or non-uniform about a point.
- **Combine**: Join, Cut or Intersect target and tools, with **Keep Tools**.
- **Split Body / Split Face**:
  - The tool is a profile, face, plane or body. The schema lists tool types constructionPlane,
    face, body and sketchEntity.
  - `extendTool` extends the tool until it fully crosses the body.
  - Split-face types: surface intersection, along vector, closest point.
- **Mirror**: features, faces, bodies or components about a plane; Join stitches the result.
- **Patterns**:
  - Rectangular: two directions, each with count, spacing or extent, and symmetric.
  - Circular: axis, count ≥ 2, total angle, symmetric.
  - On Path.
  - **Compute**: **Optimized** (fastest), **Identical**, **Adjust** (most reliable, **default**)
    [O schema].
  - Instances can be **suppressed** individually: "Check Suppression, then uncheck instances in
    the canvas" [O].

### 4.7 Hole and Thread [O]
- Placement: on a face by **edge references** or at **sketch points** (several at once).
  Position options: start, mid or end point of an edge.
- Hole type: **Simple, Counterbore, Countersink**.
- Tap type: **Simple, Clearance** (standard, fastener, size and fit close/normal/loose, from
  `HoleData/clearance.json`), **Tapped**, **Taper Tapped**.
- Extent: distance, through all, or to.
- Drill tip angle (for example 118° or 180°).
- **Thread**:
  - On a cylindrical face, modelled (real geometry) or cosmetic.
  - Standards come from `ThreadData/*.xml`, and `ThreadDataQuery` lists types, sizes,
    designations and classes.
  - High or low end location.

### 4.8 Direct edits that also live in the timeline [O]
- **Press Pull**: one tool that offsets a face, fillets an edge or extrudes a profile,
  depending on what you pick.
- **Offset Faces**, **Replace Face** (source faces to target faces), **Delete Face**,
  **Remove Features** ("fast removal of simple features like chamfers and small holes").
- **Move/Copy**: free move, translate along an entity, point to point, point to position,
  rotate.

---

## 5. History, parameters and construction geometry

### 5.1 Timeline [O API]
- An ordered list of `TimelineObject`s, each a feature, sketch or group.
- **Marker**: `rollTo(rollBefore)` moves the marker, so later features become RolledBack.
  `moveToBeginning`, `moveToEnd`, step forward and back, `play`, and
  `deleteAllAfterMarker`.
- **Reorder** with a check (`canReorder(beforeIndex)`): a feature cannot move above its
  inputs.
- **Groups** (`TimelineGroups`) and **suppress** per feature.
- Health states: Healthy, Warning, Error, Suppressed, RolledBack, Unknown. Each has a message.
  Errors do not stop later features, which carry on with whatever their inputs still resolve
  to [I].

**openRetop**: `modeling/timeline.py` has ok, failed and skipped. Add **warning**,
**suppressed** and **rolled-back**, a **marker** (edit at a point in history), and
reorder-with-dependency-check. `Feature.reads()` already gives the dependency graph.

### 5.2 Parameters [O API]
- **ModelParameters** are created automatically, one per dimension or feature value (`d1`,
  `d2`, …, with a `role` such as "distance" or "taperAngle"). **UserParameters** are named and
  have a `unit` and a `comment`.
- Every value field accepts an **expression**: a number with units, a parameter name, or
  arithmetic. The schema says: "Accepts literal with units, UserParameter name, or expression".
- Other properties: `dependentParameters`, `isFavorite`, text-valued parameters
  (`TextParameterValueType`), and CSV import and export.
- **openRetop**: store each dimension or feature value as `{expression, value}`, with a
  parameter table and an expression evaluator that is unit-aware. Python with a restricted
  AST evaluator plus `geometry/units.py` would do. A dependency sort recomputes the values.

### 5.3 Construction geometry [O API]

| Kind | Definitions |
|---|---|
| Plane | offset, at angle, tangent, tangent at point, midplane, two edges, three points, perpendicular to a path, along a path (distance), at angle on a curved face, offset through a point |
| Axis | through a cylinder, two planes, two points, an edge or line, normal to a face at a point, perpendicular at a point |
| Point | vertex, two edges, three planes, edge and plane, centre of a circle or sphere, along a path |

openRetop already has scan alignment and fitted primitives. Planes and axes taken from fitted
cylinders and planes are its equivalent of "through cylinder" and "offset from face".

---

## 6. Fusion's mesh-to-CAD workflow (closest match to openRetop) [O]

From the Mesh workspace strings (`NaParaMesh*`):

1. **Generate Face Groups** (segmentation).
   - **Fast**: "based on an angle threshold between faces".
   - **Accurate**: "matching mesh faces to simple geometric primitives".
   - Settings: **Angle Threshold**, **Boundary Tolerance**, **Minimum Face Group Size**
     (a percentage of the total mesh area).
   - Tip: run Fast first, then Accurate on selected groups.
   - Warns above **5000 faces** for Accurate.
   - Also **Combine Face Groups**, **Create Face Group** (any faces, even disconnected), and
     display by colour with Shift+F.
2. **Plane Cut**:
   - Trim, Split Body or Split Faces.
   - Fill type **No Fill, Minimal or Uniform**, to stay watertight.
3. **Create Mesh Section Sketch**:
   - Pick a body and a plane, then a "Transform Plane" step to place it.
   - Creates a sketch that holds the section polyline as reference.
   - Tip: "Create a series of mesh section sketches to reverse-engineer complex mesh bodies".
4. **Fit Curves to Mesh Section**, inside that sketch (`NaSketch10`):
   - Select the section, then **First Point** and **Second Point** on it (a sub-range).
   - **Path Direction**: Short Path or Long Path, for closed sections.
   - **Fit Curve Type**: Line, Arc, Circle, Ellipse, Spline, Closed Spline.
   - **Spline Fit Tolerance**.
   - **Match Tangent** at each end, which creates tangent constraints to the neighbour curves.
   - Readout: **Max Curve Deviation**.
   - Errors: "Include more points to fit an arc", "Failed to add tangent sketch constraint".
5. **Convert Mesh**:
   - **Prismatic**: merges face groups into single analytic faces, "face groups are used to
     infer prismatic features".
   - **Faceted**.
   - **Organic**: by accuracy Low, Medium, High or Precise, or **By Face Number**.
   - Operation: **Parametric** (a timeline feature that updates upstream) or **Base Feature**
     (a T-Spline form you can edit first).
   - Failure advice: "Use Generate Face Groups or Direct Edit to align face groups to geometric
     features".
6. **Replace with Primitives** (box, cylinder, sphere) is a separate tool.

**What openRetop can take from this**:
- Its Section Sketch auto-fits the whole section. Fusion instead fits **one span at a time**
  between two picked points, with a chosen type, match-tangent at the ends, and a live max
  deviation.
- Offering both is best: auto-fit everything, then "refit this span as…" with Fusion's
  controls for the spans the auto-fit gets wrong.
- Fusion's "Fast vs Accurate" segmentation split is the same as RE-03's region growing vs
  primitive classification.
- "Convert Mesh → Prismatic" is effectively RE-08 (primitives to solid).

---

## 7. Priorities for openRetop (suggested order)

1. **Parameters and expressions** behind every dimension and feature value (§5.2). Everything
   else in Fusion's parametric feel depends on this.
2. **Sketch drawing UX**: heads-up fields, inference glyphs, and the blue-to-black colouring
   (openRetop already computes `fully_defined()`) (§1.2).
3. **Extrude parity**: To Object (and up to the scan), Through All, Symmetric per side,
   Two Sides with separate taper, Start Offset, Thin, participant bodies (§4.1).
4. **Fillet and Chamfer** with selection-set rows. These already exist as S-15 in the plan;
   copy Fusion's defaults (§4.4).
5. **Timeline marker, suppress and health states** (§5.1).
6. **AutoConstrain**, heuristic only, for fitted section sketches (§3).
7. **Per-span refit** in the section sketch, as in Fusion's Fit Curves to Mesh Section (§6).
8. Revolve from a centerline (linear-diameter dimensions), Shell, Patterns, Mirror, Hole.

---

## 8. What is not known

| Question | Why | How to settle |
|---|---|---|
| Numeric inference tolerances: how close to horizontal snaps to H, the snap radius in pixels | Compiled into NaSketch and not exposed | Measure in the app: drag slowly off-axis and note the angle where the glyph disappears |
| AutoConstrain priority values and zone thresholds | Compiled into the engine | Not needed. Tune against openRetop's own benchmarks |
| VCS internals (decomposition details, tolerances) | Proprietary; only strings were examined | Not needed; §2 gives the design |
| Default Operation for a second extrude | Only the first extrude was observed (New Body) | Extrude onto an existing body and look |
| Extrude Direction, Extent and Operation dropdowns on screen | Esc cancelled the dialog before they were captured; the lists here come from the API enums | Open them in the app |
