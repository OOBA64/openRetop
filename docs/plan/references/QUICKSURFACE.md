# QuickSurface reverse-engineering toolset: reference for openRetop

QuickSurface (KVS Ltd) is the product openRetop's [RE_PLAN.md](../RE_PLAN.md) names as its model
("an ExModel / QuickSurface Pro copy in terms of tooling and workflow"). This file records what
QuickSurface 2026 actually does, tool by tool, so the plan's tasks can copy its behaviour and
defaults instead of guessing.

- **Source.** QuickSurface 2026 (8.0.123), `C:\Program Files\KVS Ltd\QUICKSURFACE2026`. Collected
  2026-10-11.
- **How.**
  - The shipped manual `QSHelp.pdf` (256 pages), read in full.
  - The two `knowledgebase_*.md` files (the tutorial map).
  - The four AI-assistant prompt files.
  - `language.txt`, the full UI string export: 423 menu items, 674 dialog items, 1,789 string
    table and source strings.
  - String and library inventories of `QuickSurface.exe` and its DLLs.
- **Not examined.**
  - The live app: this install is not activated, so only the activation screen opens.
  - `QuickSurface.exe` internals: it is packed or protected (each DLL has a single static
    import), so its code was not unpacked or decompiled.
- **Use it as a behaviour spec.** The manual forbids reproduction, so everything below is a
  summary in our own words. Labels in quotes are UI strings, which are needed to match the
  feature names.
- **Confidence tags.** **[O]** observed in the manual, strings or files. **[D]** derived from
  several observations. **[I]** inferred; check it before relying on it.

---

## 0. What QuickSurface is built on [O]

| Component | Evidence | Meaning for openRetop |
|---|---|---|
| **OpenCASCADE** (TKBO, TKBool, TKFillet, TKOffset, TKFeat, TKShHealing, TKSTEP, TKIGES, …) | The DLLs ship next to the exe; mangled OCC names appear in its strings | **The same kernel as openRetop**, so every QuickSurface CAD operation is achievable with OCP |
| SALOME GEOM algorithms inside the exe: `Partition_Spliter/Inter2d/Inter3d/Loop2d/Loop3d`, `BlockFix_UnionFaces`, `ShHealOper_Sewing/Tool` | Exe strings | Trim and automatic trimming are a **general partition**: split every shape by every other, then keep or drop pieces. Merge faces is "union same-domain faces". Sewing comes from SALOME's healing |
| Custom OCC subclasses: `BRepFill_OffsetWireEx`, `BRepOffsetAPI_MakeOffsetEx`, `BRepMAT2d_BisectingLocusEx`, `MAT2d_Mat2dEx`, `ShapeFix_FaceEx/WireEx`, `ProjLib_ProjectOnPlaneEx`, `BRepAlgoAPI_BuilderAlgoQS` | Exe strings | Patched 2D offset (medial-axis based), projection and healing. Also uses `BRepOffsetAPI_MakeFilling`, `GeomPlate_BuildPlateSurface`, `BRepOffsetAPI_ThruSections`, `BRepOffsetAPI_MakeThickSolid`, `BRepFilletAPI_MakeFillet2d`, `GeomAPI_ProjectPointOnSurf` |
| **Parasolid** (`pskernel.dll`, 74 MB) | Imported by the exe; `PK_FACE_split_at_param` | A second kernel, use not confirmed [I]. Possibly for parametric transfer or specific operations |
| **Exoside Quad Remesher** (`xremesh.exe`, `xremeshlib.dll`) and **Instant Meshes** (`InstantMeshes.exe`) | Bundled, with their licences | Auto Freeform (quad layout of a whole scan) is built on these |
| `flatten.exe` | Bundled | Flatten Surface (unwrap a surface to a pattern) |
| PCL and VCG references, `icp` | Exe strings | Point-cloud and mesh processing; ICP for fine alignment [I] |
| Gemini AI (prompt files) | `prompt_*_gemini.md` | "AI Assistant" (§9) |

**OCC mapping for openRetop**, a direct translation of what QuickSurface uses:

| QuickSurface tool | OCC (OCP) building block |
|---|---|
| Trim / Automatic Trimming | `BRepAlgoAPI_Splitter` or `BOPAlgo_Builder` (general fuse) over all selected shapes; keep or drop pieces; then `BOPAlgo_MakerVolume` or sewing to a solid |
| Merge faces | `ShapeUpgrade_UnifySameDomain` |
| Sew selected surfaces | `BRepBuilderAPI_Sewing` |
| Fill Surface (Contact/Tangent/Curvature per edge) | `BRepOffsetAPI_MakeFilling` (GeomPlate) with `GeomAbs_C0/G1/G2` per boundary; internal curves as constraints; "On scan data" adds point constraints |
| Loft | `BRepOffsetAPI_ThruSections` (`isRuled`) or `GeomFill` for guide curves |
| Sweep / Pipe | `BRepOffsetAPI_MakePipeShell` |
| Thicken / Offset / Shell | `BRepOffsetAPI_MakeThickSolid`, `BRepOffsetAPI_MakeOffsetShape` |
| 2D sketch offset (Arc or Intersection corners) | `BRepOffsetAPI_MakeOffset` with `GeomAbs_Arc` / `GeomAbs_Intersection` |
| 2D fillet and corner trim | `BRepFilletAPI_MakeFillet2d` or `ChFi2d_FilletAPI` |
| Fillet / Chamfer on bodies | `BRepFilletAPI_MakeFillet` / `MakeChamfer` |
| Cut / Combine / Intersection of solids | `BRepAlgoAPI_Cut` / `Fuse` / `Common` |

---

## 1. Workflow (as the manual and tutorials teach it) [O]

```
Import scan (+units) → Prepare / Mesh edit (reduce, holes, outliers, noise)
  → Extract primitives (+ Auto Constrain) → Align (Primary/Secondary/Tertiary)
  → Model, in three ways that combine freely:
      A. Primitives  → Trim (manual/automatic) → solid            (machined parts)
      B. 2D Sketch from sections → fit/auto-sketch → Extrude/Revolve → Cut/Combine
      C. Freeform: Fit Surface / 3D sketch → Loft/Fill/Sweep  OR  quad Freeform / Auto Freeform
  → Fillet / Chamfer / Patterns / Mirror
  → Compare (deviation) / Straightness (rounded values) / Draft / Zebra
  → Export STEP/IGES, or live parametric transfer (QSConnect: SOLIDWORKS, Inventor, Fusion 360)
```

The recommended alignment recipes (knowledge base):
- **Plane–Cylinder–Plane** for prismatic parts with bores: base plane levels the part, then a
  main cylinder sets the axis, then a second plane locks the rotation.
- **3-Plane** for block-like parts.
- Order: Primary (levelling / Z) → Secondary (origin) → Tertiary (rotation).

---

## 2. Mesh preparation [O]

| Tool | Behaviour and defaults |
|---|---|
| **Import** | STL, OBJ, PLY, PTX, E57 and `.qsf`. Asks for units. "Map OBJ Y to Z axis" option. **PTX**: units default **metres**; "Triangulation Maximum Edge Length" is Automatic or Custom; options to swap rows/columns, convert to mesh, point sampling. Multi-scan PTX loads as one combined mesh |
| **Low-resolution mesh** | "Create Low Resolution Mesh" for display and navigation, with "Show Original". The viewer can **draw the mesh as points while navigating** above a triangle count (setting), and switches point clouds to "Adaptive Draw" above a point count |
| **Reduce Polygons** | Target as a triangle count or a percentage; Preview; "Keep original mesh". **"Deviation of original mesh"** colours the reduced mesh against the original. The string reports "If you reduce it by X%, Y% of the points will still be within Z tolerance" |
| **Mesh Edit** | Highlights boundaries and gaps in black. Counts **Individual meshes** and **Holes**; "Duplicate triangles". Tools: Delete, **Smooth selected**, Flip normals, Clipping Box, "Select all connected triangles", Cut & Create (new mesh from the selection), Copy & Create |
| **Remove outliers** | Step through the floating pieces one at a time and delete them, or clean up in bulk **by maximum triangle count** or **by area smaller than** (click a piece to measure it), or "Leave selected only". For point clouds: "Remove outlier points" by "Outlier deviation", with an "Auto guess value" |
| **Fill Holes** | Step through holes and fill one, or **fill all holes smaller than a measured size** ("Fill multiple holes", "Diameter of bounding sphere"). Algorithms: **Automatic** (fewer than **40** boundary edges → **Tangent**, otherwise **Curvature**), Tangent (flatter), Curvature (filleted). **Expand** deletes the ring of triangles round the hole first, so the fill follows cleaner data. **Smooth** rounds out a ragged boundary. **Fill Semi-hole**: draw chords to split a long narrow hole into smaller ones (Ctrl+drag). **Bridge**: draw lines across a gap to connect two parts (Shift+drag). "Improve holes' boundaries" option |
| **Reduce Noise** | "Iterations", "Apply on selection only", "Apply on boundary edges" (all in the 2026 build) |
| **Split mesh** | With another body or mesh, **Cut** (solids only: boolean-subtract a primitive, for example to make a clean bore), **Combine** (union with a primitive). Typical use: "defeature" a bad hole (delete the region, fill it, cut a fitted cylinder) |
| **Multi-scan** | N-Points align, then Fine align, then **Global Fine Align** (search tolerance, all scans move at once), then **Re-polygonize** (search tolerance; about 0.5–0.6 suited the example part; 0.1 for parts about 1 in). Gives one watertight mesh. **Merge** only concatenates, and it cannot be undone. **Average Mesh** makes a "Golden Mesh" from overlapping scans of the same shape |
| **Unroll** / **Roll Sketch** | Unrolls a mesh about a reference cylinder and angle; sketches can be rolled back on |
| **Prepare Scan**, **Scale** | Listed in the menus; not documented in the manual |

**openRetop gaps** (RE-23): outlier removal by size or area, fill-all-holes-below-size with
tangent/curvature choice and the 40-edge rule, Expand-then-fill, the "% of points within
tolerance" readout for reduction, and Re-polygonize for merging scans.

---

## 3. Selection on the scan [O]

- **Magic Wand** (W): curvature/angle region grow from a click. A sensitivity slider in degrees
  (Ctrl+wheel), where higher reaches into corners.
- Free Hand (Filled) brush (B), Free Hand, Line, Rectangle, Circle.
- **Select Through** (U): also selects back-facing triangles.
- Alt+drag deselects. Enlarge and Shrink selection. Isolate, Hide selected, Invert,
  Invert hidden, Select all connected.
- **Save Selection Status**: a named selection stored under the mesh in the tree.
- A quick toolbar appears at the cursor after a selection.

openRetop S-05 has region grow and brush. Add **Select Through**, **Enlarge/Shrink**,
**named saved selections**, and the floating quick toolbar.

---

## 4. Primitives and alignment [O]

### 4.1 Extract Primitives
1. Select an area. Wand plus brush is recommended, avoiding corners and fillets.
2. Pick the type: **Plane, Cylinder, Cone, Sphere, Reference Line** ("Fit Ref Line", Shift+L).
   - A live preview appears.
   - **Analysis** shows a deviation map of the fit.
3. Pick a constraint from a drop-down. The default is "Not constrained". The options include:
   - parallel or perpendicular to a world plane or axis, or to another primitive;
   - "Parallel to cylinder";
   - **Coincident axis** (concentric).

   The fit is then re-solved under that constraint.
4. Other options: **Solid** (caps a cylinder or cone so it is a closed body), **Lock** (only
   resizable afterwards), "Show primitives labels".
5. Messages:
   - "Failed to fit cone. It is more suitable to be a cylinder." Detect near-zero cone angles.
   - "Create primitives transparent" (a setting).

**Auto Constrain**:
- **Tilt tolerance** (degrees): if the fitted axis or normal is within it of a world axis or an
  existing primitive's, make it exactly parallel or perpendicular.
- **Coincidence tolerance** (length): if the axis passes within it of a world axis or another
  axis, make it coincident. The manual's example uses **1 mm**.
- Auto Constrain picks the relation itself (for example "Parallel to OXY"). The analysis then
  shows the extra deviation the constraint costs.

**Construct and edit primitives**:
- **Plane**: three modes:
  - Type-in (position, offset, rotation, normal).
  - From another plane (tilt, rotate, offset).
  - Constructed: middle plane of two planes, perpendicular to a primitive, from two primitives,
    three points.

  Also, from the menus: plane from the current view, **plane along a path**, **plane through a
  sketch line**, and a plane from a CAD face.
- **Cylinder**: type-in (base point, direction, radius, length), or from another cylinder or
  cone ("Coincident with" plus a new radius), "Align to closest axis", from a CAD face.
- **Cone**: type-in (semi-angle). **Sphere**: type-in or from another sphere.
- **Symmetry plane**:
  - Mark points along the visual symmetry line, or "Define Interactive" (drag a line).
  - **Rebuild** optimises the plane so the mirrored points overlap the mesh.
  - Mirrored points are shown in yellow, with live analysis.
  - The fit can be limited to the selected triangles.
- **Reference line**:
  - Type-in, or picked on the scan.
  - From two primitives: plane∩plane = the intersection line; plane + cylinder = the axis
    projected onto the plane; two cylinders or lines = the common transversal.
  - "From other primitives (average line)" gives the mean axis of near-concentric cylinders.
  - "Extract visible cylinders centre line".
- **Reference point**: type-in, line midpoint, from primitives, **three planes**.
- On-canvas editing: arrow handles resize a plane's sides, plus rotate and drag-normal handles.
  Double-click re-opens the dialog. **Replace** swaps the primitive and keeps its dependants.

### 4.2 Alignment
- **Align by Coordinate System**:
  - Pick **Primary**, **Secondary** and **Tertiary** features (point, line, axis, plane,
    cylinder, sphere).
  - A preview triad shows constrained axes in **black**, and "fully defined" once enough is
    picked. Options: choose the plane pair (OYZ vs OXZ), Flip, and a **Translate X/Y/Z** offset.
  - "Don't move the coordinate system to the centre of the primitive".
  - "Apply on imported CAD" / "Apply on all features".
- **Align Interactive**:
  - Manipulator with a drag-strength slider; step rotations in 1° increments about a chosen
    axis.
  - **"As Current View"** sets the axes from the current camera.
  - **"Show mirrored mesh"** mirrors about OYZ live, a visual symmetry check.
- **N-Points**: at least 3 corresponding points, spread out, in the same order on both
  objects; then Preview.
- **Fine-align reference mesh**:
  - Best fit of the mesh to a CAD model or another mesh within a **Search tolerance** (default
    **3 mm** in the tutorial).
  - If triangles are selected, **only the selected areas** take part (areas of interest).
- **Global Fine Align**: all scans together.

**openRetop**: H-01 Align to World is built (a950e3a): plane / axis / origin rows, per-row
target and Flip, a preview triad, one undo step. Still to add: the **black-axis "constrained"
feedback**, **Translate offsets**, the **Plane–Cylinder–Plane** order (a cylinder as the
*second* pick setting the axis; openRetop takes a hole as the origin), **N-points + fine align**
(ICP with area weighting), and **Auto Constrain with tilt and coincidence tolerances** on
every fitted primitive (H-02 / RE-06).

---

## 5. 2D Sketch from the scan [O]

### 5.1 Creating the section ("Create Sketch")
- **For Extruded Surface** (default; OXY): the section plane translates.
  - Pick OXY, OYZ or OXZ, a primitive, or **Define Interactive** (two clicks on screen).
  - Drag it, or type an Offset.
  - "Automatically snap to X or Y direction".
- **For Revolved Surface**: the plane rotates about an axis (X/Y/Z or a picked cylinder) and
  automatically adds a **construction centre line** for Revolve.
- Point display: **white = actual section points; grey = projected onto the sketch plane**.
  "Create sketch on slicing plane" puts the sketch on the section itself instead of the
  reference plane.
- **Stacked sections**:
  - Default **20** sections (the tutorial goes to 200) across the extent of the selected
    region, or over 360° for revolved sections.
  - Two drag handles set the range.
  - All the sections' points are projected onto one sketch, which gives much denser data for
    fitting.
- **Through selection only**: section points come only from the selected triangles.
- **Outline Mesh**:
  - The silhouette of the whole mesh projected onto the plane, at any offset, instead of a cut.
  - "Ignore small segments of N points" removes stray bits.
- "Hide scan data when creating a sketch". "Sketch assist" and "Quick sketch assist" (2026,
  not documented). "Ignore scan data". "Flip orientation". "Cloud Capture".
- **Multiple sections** (for Loft):
  - Plane, offset and **Spacing**; "Curve guided" sections along a guide curve.
  - "Close section curves".
  - "Reconstructed Freeform curves": None, **Approximate within** (a tolerance), or **Build
    with** (N points). Each section becomes a fitted spline.

### 5.2 Fitting sketch entities to the section points
- **Brush fitting**:
  - **Shift + brush** over points fits a **line or arc chosen by curvature**.
  - **Ctrl+Shift + brush** always fits a line.
  - In "Fit primitives" mode a brush tool (size via Ctrl+wheel) offers Fit **Line, Arc, Circle,
    Rectangle, Slot, Hexagon, Curve**. A **radial icon menu** pops up after painting.
- Fit-primitives options:
  - **"Instant Fit"**: fit as soon as the brush is released; hold Shift to suspend it.
  - **Target tolerance**.
  - **"Make line horizontal/vertical if less than"** an angle (the manual describes it as a
    0.5 threshold).
  - **Instant join** with a **Minimum fillet radius**.
- **Auto Sketch** ("Extract lines/arcs or curves automatically from the reference points"):
  - Colours point runs: **orange = line, white = arc**. Preview, then Create.
  - Parameters:
    - **Segmentation** (higher = fewer, larger entities).
    - **Data Noise** (higher = small arcs merge into larger ones).
    - **Merge section polygons** (bridge data gaps up to a length).
    - **Features to extract**: Line/Arcs or curves.
    - **Minimum arc/circle radius**.
    - **Ignore fillets**.
  - After the preview, gaps can be painted to force a line there.
- **Freeform curve**: a spline through clicked points. "Rebuild Curve" (N points, "Snap new
  points to the mesh"). Control points shown. Dragging the end control point gives tangency to a
  line.
- **Splines fit**: **Approximate within** (tolerance) or **Build with** (N points).
- **Toleranced display**:
  - Colours each entity **green where within the tolerance of the data points, red where
    not**.
  - The tolerance example is **0.05 mm**.
  - Pass/Fail is recommended over Gradient.
- **Corner tools**:
  - **Ctrl + brush over two end points**: if they don't meet, **extend and intersect** them;
    if they already share a point, make an **auto fillet** of the radius measured from the
    data.
  - Corner Trim dialog: Corner Trim, **Auto Fillet** (radius detected, plus "Automatically add
    dimension"), **Fixed Size Fillet**.
  - A fillet can be dragged to resize it afterwards.
  - The corner tools don't work on freeform curves.
- **Trim**: paint over the unwanted pieces (an erase brush), T.
- **Constraints**:
  - Dots at end points: **orange = unconstrained, blue = constrained** (moves with its
    partners).
  - Constraints are added automatically while drawing when "Constraints" is on (snap to axes
    and to other entities).
  - On click: big symbols are offered constraints, small symbols are applied ones. Delete a
    symbol to unsnap.
  - Available: Horizontal, Vertical, Tangent, Parallel, Collinear, Equal, Perpendicular,
    Symmetric (about a construction line), Fix position, For Construction.
  - "Select overdefining constraints".
- **Dimensions**: click an arc for its radius (an input box appears), two points for distance
  (aligned, horizontal or vertical by dragging), two lines for an angle. "Circular
  dimensioning" setting: diameter vs radius.
- **Edit**:
  - **Offset**: Flip; corners as **Arc** or **Intersection**; "Two sided".
  - **Mirror** about a construction line (copy only, no symmetry relation).
  - **Duplicate**: Linear (axis or picked line, Instances including the original, Spacing,
    Flip), Grid (Direction 2), **Circular** (centre point, Instances, "Angle to fill" default
    360, "Retain original orientation", Skip instances), "Along curve" with "Equal spacing".
    Copies are independent, not linked.
  - **Project sketch** (2026): Entities, **Intersection curve**, **Silhouette**.
  - Auto Join; "Round circle radius to"; Orthogonal/Tangential tolerance (2026 clean-up options).
  - "Clean up reference points", "Clip".
- **Export**: DXF R12/R14 (R14 recommended, for splines; DXF is always in mm), IGES.

**openRetop**: S-13 and RE-11..14 already plan "brush-to-fit line/arc/circle within a
tolerance, H/V snapping, corner radii". Concrete additions from QuickSurface:
- curvature-based line-vs-arc choice on Shift-brush;
- the Ctrl-brush **intersect, then fillet** corner gesture;
- **Toleranced green/red per entity** against the section points;
- **Auto Sketch** with Segmentation, Data Noise and gap-merge parameters;
- **stacked sections** and **outline mesh** as section sources.

---

## 6. CAD features [O]

| Feature | Behaviour and options |
|---|---|
| **Extruded** | From a closed (or open, for a surface) sketch. Options: **Solid** (vs surface), **Depth 1** (top) and **Depth 2** (bottom), both positive from the sketch plane; **Up to** (a primitive or face); **Draft angle**; **Inverse**; "Set sketch on Top/Bottom plane" (re-bases the sketch so depths can pass it); "Full depth". **Snapping**: a live deviation colour of the new walls against the scan while dragging the depth handles, with a **yellow snap point** when the cursor is inside the mesh (snaps to the planes there). **Advanced, "Optimise to selected points"**: with triangles selected, fit the top or bottom cap plane to them (a one-off). "Labels" |
| **Draft extrude** | Typed draft angle, adjusted against the snapping colours (tutorial: 1°) |
| **Revolved** | Axis picked, or **automatically the only construction line in the sketch**. **Full** (default) or **Partial** with **Angle 1/Angle 2** handles; **Snapping** colours; **Inverse** |
| **Trim** (manual) | Select the shapes, then click the pieces to remove. Each shape gets its own colour. A status reads "Multiple surfaces" → "Single surface" or "Solid body". Reset trim, Show wireframes, a Visibility list per shape, **Swap visible**. Editable afterwards. Also "Merge faces", "Group faces", **"Quick solid"** |
| **Automatic Trimming** | **Tolerance** (default computed from the object size) plus **"Overlap with reference mesh"** slider (Min ↔ Max: how much of a piece must lie on the scan for it to be kept). "Apply Automatic Trimming"; then fix by hand. *This is the ExModel/QuickSurface auto-trim the plan's S-09 describes; openRetop has it, plus red open edges and "Trim again" (H-06)* |
| **Cut from selected solid** | Pick the target solid, then click the tool solids. It stays a live feature: editing a pattern of tool cylinders (5 → 10) updates the cut |
| **Combine solids / Intersection** | Boolean fuse/common. The tools must overlap (extend the cylinders into each other) |
| **Fillet / Chamfer** | Hover highlights edges; a handle at the edge midpoint drags the radius, or type it. Preview, Reset. **Toleranced** shows the fillet's deviation from the scan while dragging, which is how you *find* an unknown radius. Several edges with Ctrl. "Failed to fillet all selected edges" |
| **Patterns** | Circular: Axis (world or any primitive), Instances, Angle to fill (360), Flip rotation, Skip instances. Linear: Direction (axis or any primitive), Instances, Spacing, Flip, Direction 2 (grid). Patterns are parametric and live in the tree |
| **Mirror body** | About a world or user plane; the result is **merged automatically** with the original |
| **Move body** | Manipulator, drag strength, step rotate/translate, **Create copy**. The copy is **parametric**: it follows edits to the original |
| **Other CAD (2026)** | Shell (draft angle option), Split solid, Scale body, Delete faces, **Move face** (with tangent faces, left/centre/right side faces), Duplicate face, 2D sketch on a CAD face, Separate multibody, "Plane from 2D sketch" |
| **Helix / threads** | Axis (picked from a CAD face), **Pitch** (default 1 mm; **Measure Pitch** by picking two crests), start and end points picked on the scan (not at the very ends), **Auto Adjust** (fixes the pitch so the ends land on the curve), taper angle, **Extend start/end**: Straight (default), Natural (one more turn), Radial in/out (slider %). Then Sweep the thread profile along it as a solid and Combine |

**openRetop** (S-14..S-17, RE-15/16) already plans extrude with "up to scan", live
deviation, and Auto fillet radius. Concrete details to copy:
- Depth 1 and Depth 2 as two positive values with handles.
- **Snapping** colouring plus the yellow snap point.
- **Optimise cap to selected triangles**.
- Revolve picks the sketch's single construction line automatically.
- Automatic trimming with tolerance and overlap.
- Cut features that stay linked to patterns.

---

## 7. Surfaces and freeform [O]

### 7.1 Fit Surface (openRetop S-01, S-06)
- Select the area. **Method** (drop-down), **U × V**, **default 10 × 10**.
- **Surface orientation**: default **"Selection bounds"** (minimum bounding box of the
  selection), or aligned to an axis.
- **Surface smoothness** slider (smoother means more deviation).
- **Degree / Max degree**.
- **Automatic Fit** ("Auto…", "Automatically find the best U and V"): raises U and V until the
  **Target tolerance** is met, up to **50 × 50**.
- "Fit with the new parameters" re-fits. **Analysis** gives a deviation map; Create once it is
  green.
- Fit Surface Options (for Fill too): UV Count, Smoothing, **Axis aligned**.

### 7.2 3D Sketch (curves on the scan; openRetop S-07)
- Add curve (click points; double-click or right-click Finish). **Snap Mode ON** puts points on
  the mesh. "Pick points through mesh".
- Point manipulator frames: **Local** (along the curve tangent), World, Screen; drag strength.
- **Add Blend Curve**: a G1 connector between two curves that stays attached.
- **Mesh display**: **Offset** (the mesh drawn sunk behind the curves, so they stay visible) or
  Transparent.
- **Toleranced display of curves**: Pass/Fail or Gradient, default tolerance **0.05 mm**.
  Double-click inserts points to pull a red section onto the scan.
- **Fit On Surface**: automatic internal points snapped to the mesh. Delete internal points.
- Join curves (J), Break, Rebuild curve (N points, snap to mesh), Align curve, **Match curve**,
  **Match Ortho**, Tangent/Curvature at joins.
- **Grid network**: a curve network whose intersections are the only control points, used to
  frame Fill and Loft.
- "3D Sketch from mesh and surface", "3D Sketch from selected/all", "From 2D Sketch",
  "Intersect Mesh/Surface".

### 7.3 Loft, Sweep, Pipe, Extend, Fill, Blend
- **Loft**:
  - Sections picked in order (manual, for mixed open and closed sections) or **automatic** (all
    selected, best for open sections).
  - Options: Solid, **Ruled**, **Edge chain**, **Expand by** (oversize for later trimming),
    Closed, **Tangency weight**, **Add tangent edges**, **Vertex matching**, **Guide curves**,
    Auto join.
- **Sweep**: profile and guide, Solid, **Normal constrain**, **Fix profile orientation**,
  **Twist 1/2**, **Align to Section Topology**. Error: "If the path is closed, it needs to be
  smooth" (red points show where).
- **Pipe**: radius along an edge or chain; Solid.
- **Bend pipe** (experimental): "Pick cylinders in order", Lookup tolerance, Fix first.
- **Extend Surface**:
  - Numbered sides, each with a drag handle and a typed amount.
  - **Extend type**: Auto, Perpendicular or Follow edge [O strings].
  - For oversizing before trimming against an extruded outline sketch.
- **Fill Surface** (openRetop S-08):
  - Pick the boundary curves (Select edge chain). Each side is numbered and starts as
    **Contact**; per side **Contact / Tangent / Curvature**, or **All Contact / All Tangent /
    All Curvature**.
  - **Pick internal curves** to pull the interior onto the scan.
  - **Planar Surface**.
  - **Untrimmed surface** (extend past the boundary).
  - **Surface degree**.
  - **Smooth**: an internal curve made smooth gives continuity across two fills; check with
    zebra.
  - **On scan data**: the boundary is projected onto the scan, so a rough 3D sketch is enough.
  - Fill re-generates when the 3D sketch is edited.
  - "Don't merge same curvature faces".
- **Blend Surface** (experimental): select the facing edges of two surfaces to get a
  connecting surface.
- **Sew selected surfaces**: knit into a single surface or solid.

### 7.4 Quad Freeform (SubD-style), on-scan
- New Freeform: **Add 4 Sided Face** (four clicks) or **Add Rectangular Face**.
- **Selection** modes: Points/Edges (default), Points only, Edges only, Faces only,
  Point/Edge/Face, Boundary.
- **Manipulator**: World (default), Screen, Local. **Drag strength**.
- **Snap Mode** ON: points snap to the scan.
  - **Snapping type**: **Closest Point** or **Ray Projection** (puts points where clicked;
    used for hidden or missing data; "Snap all to the mesh" uses ray projection).
- Building out:
  - **Duplicate handle "D"** on an edge: drag it out to extrude new quads.
  - Alt+drag an arrow for the same.
  - Ctrl+Alt+drag the grey square: an extension that stays tangent.
- **Irregular points** (valence ≠ 4) are shown red. Clicking the red message moves the point
  inside and adds quads so the surface stays smooth.
- **Bridge Edges** (D) between two chains with the same edge count. **Merge** by dragging one
  edge onto another. **Close 4-sided hole**.
- **Split** (S): insert an edge loop.
- **Increase Resolution** (Ctrl+R): each quad becomes four.
- **Smooth** (Q, repeatable) on an edge chain, or the **brush smooth** (Ctrl+Shift+drag;
  wheel sets the size).
- **Snap to Mesh**.
- **Crease** and Remove Crease, for edges, chains or single points. A crease on one edge fades
  out smoothly.
- **Align Horizontally / Vertically** (an edge chain onto a positioned segment).
- **Symmetry**: OXY/OYZ/OXZ mirror, with "Set On Symmetry Plane" for the middle chain (it stays
  on the plane and forms a bridge strip).
- Control Net display, **"Don't move neighbours"**, Surface Transparency.
- **Toleranced display** (Pass/Fail/Gradient) and **Zebra**.
- **Offset** (also "Offset boundary to surface", "Offset based on other primitives").
- Templates: save the quad cage, then load it onto another scan.
- **Export**: patches are merged along the "white" borders. Only the true boundaries (white)
  become surface edges, so the export has *few* B-spline faces, not one per quad. QuickSurface
  presents this as a selling point.
- **Wrap Surface**: fits a cylinder to the selection, makes a quad grid around it, and
  projects it onto the mesh. Details **Low / Medium / Fine**.
- **Merge** quad surfaces (tree).
- **Thicken Freeform**: Thickness, Outward. The tutorial advises instead: Copy, then Offset,
  then brush-smooth the creases, then Flip the original, Merge both, Bridge the boundary edges,
  and Crease them for sharp corners.

### 7.5 Auto Freeform ("Automatic Surfacing")
- **Target Quads Count**: **Low 1000 / Medium 2000 / Fine 4000 / Custom** (the example gave
  3949 at Medium).
- **Feature Details**: default **Balanced** (higher is slower).
- **Symmetry plane**. Preview. Shows the actual number of quads.
- Needs a good watertight, mostly organic mesh; prismatic parts give poor results.
- "Draw guide curves on the mesh", "Extract from selected triangles only".
- Built on the bundled quad remeshers (§0) [I].

### 7.6 Hybrid CAD (2026, new) [O strings]
"Create Hybrid CAD automatically from scan data by combining analytic primitives with
intelligently generated freeform surfaces." It "will use the available surfaces, solids or
primitives and will create a hybrid model."

Options seen: **"Round fillets to be ignored"**, **"Freeform complexity"**. This is
QuickSurface's one-click scan-to-solid: fitted primitives plus automatic freeform for the
rest, trimmed together. It corresponds to openRetop RE-25 and beyond [I].

---

## 8. Analysis and tree [O]

- **Compare**:
  - The CAD is tessellated, then each scan point's distance is coloured with a **Tolerance (±)**
    band. Points outside the max are black.
  - Hover for the value; click to place labels for reports; Clear Labels; Show Min/Max.
  - "Select all points in tolerance".
  - Compare method choice. Export.
  - **Compare to other meshes** (scan vs scan).
  - "Deviation tolerance cannot be zero and will be automatically set to 0.001".
- **Straightness** (manufacturability):
  - Checks each primitive's **position**, **tilt angle** and **diameter** for whether they are
    round numbers to N **decimal places** ("Arithmetic Precision"; examples: 1, 3, 15 → 0.5,
    2.7, 15.9 → …).
  - Yellow means not round; hover explains which value.
  - *Strongly recommended for openRetop* alongside RE-06 rounding.
- **Draft analysis**: reference plane or primitive, angle, Flip; positive / needs-draft /
  negative colours.
- **Zebra** (width, horizontal/vertical, colour), **Environment map**, **Measure** (3D distance,
  extended distance, curve length), **Surface area**, **Volume**.
- **Objects tree / History**:
  - Two views: creation order, and **parent-child**. Expand/Collapse all.
  - **Rebuild** replays the whole history.
  - **"-> Disable All Next" / "<- Enable To Here"**: suppress everything after an item so
    edits rebuild only up to it. Disabled items are shown in italics.
  - 2026 adds an **"End Of Model" marker** with "Place at Start/End" (a rollback bar) and a
    "Dual features tree".
  - "The parent feature is missing. Select the parent from the existing features list": broken
    references are repaired by re-picking.
  - Undo is **one step** for most operations.
- **QSConnect**:
  - Live transfer of the parametric tree to SOLIDWORKS (step by step; it pauses after each
    Trim for review; Map Z→Y; freeform goes as an external IGES), Inventor, Fusion 360, JCD,
    Verisurf.
  - At the end it asks to knit to a solid.

---

## 9. AI Assistant (2026) [O]

Two modes, both send **viewport images** to Google Gemini, with a consent note: "captures
images of your data … AI can make mistakes".
1. **"How do I make this part?"**
   - Identifies the object (name in bold uppercase).
   - Lists its geometric **features**, each with the CAD operations needed ("Square base: 2D
     sketch + extrude").
   - Then a de-duplicated list of the relevant tutorials.
2. **"How to align the scan data?"**
   - From the top, left, front and iso views with the axis triad, judges whether the dominant
     planes and axes are parallel to XYZ (aligned or not).
   - If not, names the strategy (Plane–Cylinder–Plane or 3-Plane) and lists the steps in
     Primary → Secondary → Tertiary order.

**For openRetop** [I]: a cheap, high-value guidance feature. The orthographic snapshots and the
fitted primitives already exist. A Claude call with the same structure (identify → features →
operations → which openRetop tools, plus an alignment check) fits the workflow stepper
(RE-24). Show the same consent note.

---

## 10. Gap list for openRetop, mapped to plan IDs

| Plan ID | QuickSurface behaviour to copy |
|---|---|
| RE-05/06 | Auto Constrain with **tilt (deg)** and **coincidence (mm, e.g. 1)** tolerances; constraint drop-down (parallel/perpendicular to world or primitive, coincident axis); Solid caps; Lock; cone→cylinder fallback |
| RE-22 | Primary/Secondary/Tertiary with **black = constrained axes**, Translate offset, plane-pair choice, "as current view", **show mirrored mesh**; N-points + **area-weighted fine align** |
| RE-23 | Outliers by size/area; fill-holes-below-size (Tangent/Curvature, 40-edge rule), Expand, semi-hole and bridge; reduce with "% within tolerance"; Reduce Noise; Re-polygonize |
| S-05 | Select Through, Enlarge/Shrink, saved named selections, quick toolbar |
| S-13 | Stacked sections (20) and range handles; Through-selection-only; Outline Mesh; white vs grey points; Shift-brush with curvature-based type; Ctrl-brush intersect→fillet; Auto Sketch (Segmentation, Data Noise, gap merge, min radius, ignore fillets); Toleranced green/red; offset Arc/Intersection |
| S-14 | Depth 1/2 handles, Up to, Inverse, **Snapping colours + yellow snap point**, optimise cap to selected triangles; revolve with an auto-picked construction axis, Partial with two angles |
| S-09 | Automatic trimming = **partition everything** (`BRepAlgoAPI_Splitter`) + keep pieces by **overlap with the scan** above a slider threshold within a tolerance (size-based default); then click to fix; "Multiple surfaces → Solid body" status |
| S-15 | Fillet Toleranced (live deviation while dragging the radius) to find the radius |
| S-01/S-06 | Fit Surface 10×10 default, Selection-bounds orientation, Auto up to 50×50 to a target tolerance, Smoothness, Max degree |
| S-08 | Fill per-side Contact/Tangent/Curvature, internal curves, On scan data, Untrimmed, Planar |
| S-10 / RE-09 | Compare ±tolerance with black outliers, labels, min/max, "in tolerance" select; **Straightness** decimal-rounding check |
| RE-07 | Disable-all-next / enable-to-here, End-of-Model marker, parent-child tree, re-pick a missing parent |
| RE-24/25 | AI assistant (identify → features → tools; alignment check); Hybrid CAD as the long-term one-click goal |

---

## 11. Not known

| Question | Why | How to settle |
|---|---|---|
| Numeric defaults of Auto Constrain tolerances, Fit Primitives target tolerance, H/V threshold, Auto Sketch sliders, automatic-trim tolerance formula | Not in the manual or strings; the app is unactivated; the exe is protected | Activate the trial and open each dialog, or watch the tutorial videos linked in `knowledgebase_general.md` |
| What Parasolid is used for | Only one Parasolid symbol was visible | Not needed for openRetop |
| Hybrid CAD algorithm | New in 2026, undocumented | Trial run on `basic_part.stl` and `aerosol_knob.stl` |
| Prepare Scan, Sketch assist, Unroll details | Undocumented menu items | Trial run |

**Benchmark data.** The install ships scans that openRetop can use for parity tests:
`basic_part.stl` **with a matching CAD `basic_part_aligned.stp`**, `aerosol_knob.stl`,
`bearinghousing.stl`, `impeller.stl`, `machine_part.stl`, `lego.stl`, `steel.stl`, `tool.stl`,
`yholder.stl`, `qsm.stl`. Check their licence before committing any into the repo. Referencing
them from the install path in a local benchmark is fine.
