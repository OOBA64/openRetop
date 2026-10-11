# Rhino 8 feature reference for openRetop

This is what Rhino 8 does in the features that matter to openRetop, recovered from the
installed program. Use it so implementation choices are not guesses.

- **Source.** Rhino 8, `8.35.26251.13001`, Windows x64, at `C:\Program Files\Rhino 8`.
  Collected 2026-10-11.
- **How.** The public RhinoCommon API and its shipped XML docs, the commands' option
  prompts, and the plug-ins' observable behaviour and settings.
- **Use it as a behaviour spec.** It records parameters, defaults, pipelines and data flow.
  No Rhino or McNeel code is copied here, and none should be; internal
  names are left out. Implement from this description and from the public papers and libraries
  named below. The QuadRemesh engine is a licensed third-party product (Exoside "Quad
  Remesher"); only its interface is described.
- **Confidence tags.** **[O]** observed directly (a documented default, a command option or
  setting, or behaviour). **[D]** derived from several observations. **[I]** inferred, so check it before you
  rely on it.

---

## 0. Quick map: Rhino feature to openRetop use

| Rhino feature | Where it lives | Engine | openRetop use | Section |
|---|---|---|---|---|
| ShrinkWrap | `Plug-ins/ShrinkWrap.rhp` (.NET), `ShrinkWrapLib.dll` (C++) | OpenVDB 9.0 + TBB | Mesh prep: close holes, unify shells and point clouds into one watertight mesh (RE-23) | 1 |
| QuadRemesh | `Plug-ins/QuadRemesh/QuadRemesh.rhp` (.NET), `xremesh.exe` + `xremeshlib2.dll` | Exoside Quad Remesher (out of process) | Quad layout for freeform patches and SubD; the out-of-process pattern matches S-03 | 2 |
| ToSubD / SubD from mesh | RhinoCore, opennurbs | `ON_SubDFromMeshParameters` | QuadRemesh to SubD to NURBS route for freeform | 3 |
| Patch (fit surface) | RhinoCore | native | Same job as S-01 Fit Surface and S-08 Fill | 4 |
| NetworkSrf, Loft, Sweep2 | RhinoCore | native | S-07 Loft, RE-19 patch networks | 4 |
| ReduceMesh | `Commands.rhp` | native (quadric-style) | RE-23 decimate | 5 |
| MeshRepair, Check, FillMeshHoles, HealNakedEdges, ... | RhinoCore, `MeshTools.rhp`, `Commands.rhp` | native | RE-23 mesh preparation | 5 |
| ExtractMeshPart, SelMeshFacesByDraftAngle, crease analysis | `Commands.rhp`, `MeshCommands.rhp` | native / .NET | S-05 region selection, RE-03 segmentation | 6 |
| FitCrv, RebuildCrv, Curve.PullToMesh, Contour/Section | RhinoCore | native | S-07, S-13 section sketch | 7 |
| PointDeviation, CurvatureAnalysis | RhinoCore | native | S-10 Compare, RE-02 curvature | 8 |

---

## 1. ShrinkWrap

### 1.1 Architecture [O]
- `ShrinkWrap.rhp` is a .NET plug-in over a native wrapper of **OpenVDB 9.0** (with TBB and
  Blosc). The wrapper offers: mesh to signed-distance grid (voxel size, exterior and interior
  band in voxels, flags), points to level set (per-point radii), offset, smoothing (type,
  iterations, width), grid to mesh (iso value, adaptivity), grid booleans, blend and transform,
  all cancellable.
- The OpenVDB tools it relies on: mesh-to-volume, particles-to-level-set, the level-set filter
  and tracker, adaptive volume-to-mesh, signed flood fill and CSG.

### 1.2 Parameters and defaults
`Rhino.Geometry.ShrinkWrapParameters` (RhinoCommon ctor) [O]:

| Property | Default | Meaning |
|---|---|---|
| `TargetEdgeLength` | **1.0** (doc units) | Used directly as the **voxel size** |
| `Offset` | 0 | Signed distance. Positive grows the result outward (see 1.3 step 3) |
| `SmoothingIterations` | 0 | Number of Laplacian level-set filter passes |
| `FillHolesInInputObjects` | false | Run Mesh.FillHoles on each input mesh before voxelizing (ignored for point clouds) |
| `PolygonOptimization` | **10** (range 0..100) | Adaptivity = value × **0.002**, so 0..0.2 |
| `InflateVerticesAndPoints` | false | Treat mesh vertices as points too (8.3+) |

Command-line options of the `ShrinkWrap` command [O]: `Resolution` (≥ 0.001), `Offset`,
`Smooth` (int ≥ 0), `PolygonOptimize` (0..100), `UseVerticesAndPoints`, `FillHoles`,
`VertexColors`, `DeleteInput`, `Preview`, `DrawWires`, `HideInput`, `SaveSettings`.
Panel defaults: polygon optimisation 10, close meshes on, draw mesh wires on, spinner steps of
1.0 [O]. Legacy `VolumeParameters.SetDefaults` [O]: voxel 0.5, exterior
and interior band 3.0, iso 0.0, adaptivity 0.0.

### 1.3 Pipeline [O]
1. If `FillHolesInInputObjects`, call `mesh.FillHoles()`.
2. **Mesh to signed distance grid.** Voxel size = `TargetEdgeLength`. Exterior band 3 voxels,
   interior band 3 voxels, flags `None`. Natively [O]:
   - Both bands are clamped to at least 1.
   - The transform is a uniform scale map with a half-voxel cell-centre offset (0.5).
   - `meshToVolume` runs with the flags. The flags enum is OpenVDB's own: `UnsignedDistanceField=1`,
     `DisableIntersectingVoxelRemoval=2`, `DisableRenormalization=4`, `DisableNarrowBandTrimming=8`.
   - The mesh is first moved so its bounding-box centre sits at the origin. The grid is
     translated back afterwards, which keeps float precision far from the origin.
3. **Offset** (only if ≠ 0). Native code calls `LevelSetFilter::offset(-distance)` [O]. In
   OpenVDB a negative offset grows the surface, so the user's positive `Offset` means **outward**.
4. **Smooth** (only if iterations > 0). `Smooth(type=1, iterations, width=1)` [O].
   `SmoothType` enum [O]: `Gaussian=0, Laplacian=1, Mean=2, MeanCurvature=3, Median=4`.
   - Natively, each iteration is one `LevelSetFilter` pass: gaussian(width), laplacian(),
     mean(width) ("Mean-value flow of level set"), meanCurvature(), or median(width) [O].
   - A `LevelSetTracker` keeps the band normalized.
   - **So ShrinkWrap smoothing is N passes of Laplacian flow on the level set.**
5. **Volume to mesh.** `ToMesh(isoValue = 0.0, adaptivity = PolygonOptimization × 0.002)` calls
   `VolumeToMesh` [O].
   - Adaptivity is clamped to [0, 1].
   - `relaxDisorientedTriangles = true`.
   - The output mixes quads and triangles, and is rejected if it has no vertices or faces.
6. Point clouds use `ParticlesToLevelSet` [O] with the same voxel size and band width.
   - Radii can be per point. If the radius count ≠ the point count, the **mean radius** is used
     for every point.
   - Points are recentred on their bounding-box centre first.
   - Rhino point objects become "vertex meshes". With `InflateVerticesAndPoints`, mesh vertices
     are merged into the point cloud.

Input clean-up before voxelizing [O], in order:
1. FillHoles if the mesh is open (when requested).
2. If `SolidOrientation() == -1`, flip it.
3. `Vertices.CombineIdentical`, then `CullUnused`.
4. `CullDegenerateFaces`, then `RemoveZeroAreaFaces`.
5. Append everything into one mesh.
6. `HealNakedEdges(100 × absolute tolerance)`.
7. `ConvertQuadsToTriangles`.

Breps, extrusions and SubDs are meshed first with the given `MeshingParameters`.

Memory guard [O]:
- cells = ceil(dx/v) × ceil(dy/v) × ceil(dz/v) over the selection bounding box.
- If cells × 4 bytes ≥ **8 GiB** (8,589,934,592), the user gets "may cause system instability".
- It is skipped in scripted mode.

Progress strings [O]: "Calculating Offsets...", "Smoothing results...", "Optimizing polygons...".
Esc cancels through the interrupter.

### 1.4 How to build it in openRetop (Python)
- **Best fit: OpenVDB's Python bindings** (`pyopenvdb` / `openvdb` wheels, MPL-2.0):
  `tools.meshToLevelSet` / `createLevelSetFromPolygons`, `LevelSetFilter`, `volumeToMesh`
  with `adaptivity`. That reproduces Rhino almost one to one.
- **Fallback without OpenVDB.** A dense or blocked grid built from a signed distance field
  (`trimesh.proximity.signed_distance`, or winding-number sign for open scans), then
  Laplacian or mean-curvature smoothing on the SDF, then `skimage.measure.marching_cubes`
  (VTK `vtkFlyingEdges3D` is already a dependency), then QEM decimation in place of adaptivity.
- Run it in the kernel worker process (S-03) with a cancel flag. Rhino checks for cancellation
  between every stage.
- **For scans with holes**, an unsigned-distance shell at offset `+d` then `-d` ("morphological
  closing") is the usual shrink-wrap. Rhino's default uses *signed* distance plus
  FillHoles. Expose both modes.

---

## 2. QuadRemesh

### 2.1 Architecture [O]
- `QuadRemesh.rhp` (.NET) writes the input mesh as an **"EXO" mesh file**, writes a
  **settings text file**, starts `xremesh.exe` (`UseShellExecute=true`, `CreateNoWindow=true`),
  then polls a **progress file** every **100 ms**.
  - The progress file holds a float. 0..1 is the fraction done. **2.0 means finished.**
  - Cancelling kills the process.
  - The result is read back from the output EXO file.
- The engine is `xremeshlib2.dll` (Exoside Quad Remesher). `ChSolver.dll` sits beside it.
- This is the same "kernel worker in a separate process" design as openRetop S-03, done with
  files instead of pipes.

Settings file keys the plug-in writes [O], in order:
```
HostApp=Rhino
FileIn="<tmp in>"   FileOut="<tmp out>"   ProgressFile="<tmp progress>"
TargetQuadCount=<int>
CurvatureAdaptivness=<AdaptiveSize, invariant culture>      (sic)
ExactQuadCount=<0 if AdaptiveQuadCount else 1>
AutoDetectHardEdges=<bool>
UseIndexedNormals=<bool>
FreezeBorders=<bool>
UsePolygonGroups=0 | 1 [+ SmartMergeCADFacesGroups=1 for "Smart"]   (brep face mode off/smart/strict)
SymAxis=<"" | combination of X,Y,Z>
SymLocal=1
PreProcess_WeldPoints=1
PostProcess_SplitPointsOnCreasedNormals=1
```
These keys show the engine's stages: weld input points, optional curvature-adaptive density,
hard-edge detection, polygon groups (patch boundaries the layout must follow), local
symmetry, and a final split at creased normals.

### 2.2 Parameters and defaults
`QuadRemeshParameters` (RhinoCommon) and `QuadRemeshSettings` (plug-in) [O]:

| Parameter | Default | Notes |
|---|---|---|
| `TargetQuadCount` | **2000** | |
| `TargetEdgeLength` | 0 in the API (the plug-in stores 1.0 but only uses it when enabled) | If > 0, overrides count: *quadCount ≈ area / edgeLength²*. The XML doc formula "Area × sqr(len)" is a doc error [I]. AdaptiveSize and AdaptiveQuadCount are then ignored. In the UI it is clamped to at least the model absolute tolerance. |
| `AdaptiveSize` | **50** (0..100; the command option range is 1..100) | Larger means quad size follows curvature more |
| `AdaptiveQuadCount` | **true** | true lets the count grow in curved areas (sent as `ExactQuadCount=0`) |
| `DetectHardEdges` | **true** | |
| `UseIndexedNormals` (command option `DetectEdges`, UI only) | false | Edge loops where the input normals are unwelded |
| `PreserveMeshArrayEdgesMode` | 0 | 0 off, 1 Smart (drops small brep faces), 2 Strict |
| `SymmetryAxis` | None | Flags X/Y/Z, combinable |
| `GuideCurveInfluence` | 0 | UI list: None, Approximate, Create Edge Ring, Create Edge Loop. The API value = UI index − 1. **Docs disagree** on whether 1 is ring or loop (the parameters doc says 1 = Ring; the private curve struct says 1 = EdgeLoop). Trust the UI order: 0 Approx, 1 Ring, 2 Loop [D]. |
| Guide `CurveStrength` | float 0..1, only for Approximate | Curves are sent as control-point float arrays |

UI and command extras [O]:
- `ToSubD` (convert the result to SubD), `SubDCreases`, `SubDCorners`, `InterpSubD`.
- `RefitMeshResult`, default false.
- `WeldAngle`, default **22.5°**.
- `DeleteInput` and `HideInput`.
- Reset values: TargetQuadCount 2000, RefitMesh off, ToSubD off, SubDCrease off.

### 2.3 Post-processing done by the plug-in [O]
- **Refit to input.**
  - Compare the bounding-box volumes of the input and the remesh.
  - If they differ by more than ±0.1 %, skip, because the remesh is not comparable.
  - Otherwise move every remesh vertex to its `ClosestPoint` on the input mesh. The search
    distance is **1 % of the input bounding-box diagonal**.
- **SubD conversion**:
  - `InteriorCreaseTest` = AtMeshDoubleEdge if `SubDCreases` is on, else None.
  - `ConvexCornerTest` = AtMeshCorner if `SubDCorners` is on, with max convex angle **120°**.
  - `ConcaveCornerTest` = AtMeshCorner if on, with min concave angle **240°**.
  - `InterpolateMeshVertices` = `InterpSubD`.
  - Then `SubD.CreateFromMesh(mesh, opts)`.
- **Stats.** "Average Edge" is the mean topology-edge length, rounded to display precision.

### 2.4 How to build it in openRetop
The Exoside engine is closed and licensed, so reproduce the *behaviour* with an open
field-aligned quad remesher:
- **Instant Meshes** (Jakob et al. 2015, BSD; has a CLI). Targets: vertex or face count,
  crease angle, align to boundaries, intrinsic vs extrinsic smoothing. It maps directly onto
  TargetQuadCount, DetectHardEdges and AdaptiveSize (use its `-D` / dominant mode for adaptivity).
- **QuadWild** (Pietroni et al. 2021, GPL) for CAD-like layouts with feature lines; it
  corresponds to `UsePolygonGroups` and hard edges.
- libigl / Directional for cross fields, if you write your own.

Copy Rhino's contract around the engine:
1. Run it out of process, report progress by polling, and kill on cancel.
2. Weld points before remeshing.
3. Treat hard edges and polygon groups as constraints.
4. Optionally snap the result back to the input (closest point within 1 % of the diagonal).
5. Optionally build a SubD with the crease and corner rules above.

---

## 3. SubD from mesh, and SubD to NURBS

`SubDCreationOptions` presets [O]: 0 `Smooth`, 1 `InteriorCreases`, 2 `ConvexCornersAndInteriorCreases`,
3 `ConvexAndConcaveCornersAndInteriorCreases`.

| Option | Values and meaning |
|---|---|
| `InteriorCreaseTest` | None, or AtMeshDoubleEdge (two faces whose edges have distinct indices but identical positions) |
| `ConvexCornerTest` | None, or AtMeshCorner. A boundary vertex is a corner when its angle ≤ `MaximumConvexCornerAngleRadians` (preset 120°) and its edge count ≤ `MaximumConvexCornerEdgeCount` |
| `ConcaveCornerTest` | AtMeshCorner when the angle ≥ `MinimumConcaveCornerAngleRadians` (240°) |
| `InterpolateMeshVertices` | false: mesh vertices become control points. true: mesh vertices lie on the limit surface. `SubD.InterpolateSurfacePoints` does this solve. |

The `ToSubD` command options [O] are `ControlPoints`, `MeshCreases`, `MeshCorners`,
`SurfaceCorners`, `UseMesh`, `UseSurface`.

`SubD.ToBrep(SubDToBrepOptions)` [O doc]:
- The default is `ExtraordinaryVertexProcess = LocalG1`, unpacked faces.
- The other modes are None (smallest deviation; not G1 at extraordinary vertices), LocalG1x,
  LocalG1xx and LocalG2.
- Away from extraordinary vertices, each regular quad gives an exact bicubic B-spline patch.

**openRetop route for freeform areas** [I]: brushed region, quad remesh (2), Catmull–Clark
control net with interpolation (3), bicubic patches with G1 at extraordinary vertices, then an
OCC `Geom_BSplineSurface` per face, sewn. Patches between regular vertices can be written
exactly; only the extraordinary vertices need the "LocalG1" fix.

---

## 4. Surface fitting: Patch, NetworkSrf, Loft, Sweep

### 4.1 Patch. This is Rhino's version of "fit a surface to scan data"
- **Inputs** [O doc]: any mix of curves, brep trims (sampled for points *and* normals), points,
  point clouds and meshes.
- **Full parameter set** (`Brep.CreatePatch`, all controls):
  - `startingSurface`, or a least-squares plane with `uSpans` × `vSpans`.
  - `trim`: find the outer loop among the curves and trim to it.
  - `tangency`: match the normals of the surfaces whose trims are in the outer loop (G1 to neighbours).
  - `pointSpacing`: the sampling distance on curves.
  - `flexibility`: "Lower numbers make the surface behave more like a stiff material, higher,
    less like a stiff material". The command calls it **`Stiffness`**.
  - `surfacePull`: how strongly the result is pulled toward the starting surface.
  - `fixEdges[4]`: freeze each starting-surface edge.
  - `tolerance`.
- Command and test-command options [O]: `USpans`, `VSpans`, `PointSpacing`, `SurfacePull`,
  `Stiffness`, `AdjustTangency`, `AutoTrim`, `StartingSurface`, and "Select starting surface
  <use plane>".
- **Command defaults** (`-Patch`, read in Rhino 8 on 2026-10-11) [O]: `PointSpacing=1`,
  `USpans=10`, `VSpans=10`, `Stiffness=1`, `AdjustTangency=Yes`, `AutomaticTrim=Yes`, plus
  `Preview` and `StartingSurface` options. `SurfacePull` did not appear in that prompt; it
  belongs to the starting-surface path.
- **Mapping:** this is S-01 + S-08 + RE-19 together.
  - Starting surface = an oversized plane, or a previously fitted surface (ExModel "expand").
  - Least-squares B-spline fit, plus a thin-plate "stiffness" smoothing term weighted by
    `flexibility`.
  - A pull toward the starting surface (`surfacePull`) acts as regularization where data is missing.
  - Boundary rows of control points are fixed for `fixEdges`.
  - The tangent-plane constraint along trims gives `tangency`.

### 4.2 NetworkSrf [O]
- `NurbsSurface.CreateNetworkSurface(uCurves, uContStart, uContEnd, vCurves, vContStart,
  vContEnd, edgeTol, interiorTol, angleTol, out error)`.
- Continuity codes: 0 loose, 1 position, 2 tangent, 3 curvature.
- Error codes: 1 sort failed, 2 network initialisation failed, 3 build failed, 4 invalid result.
- Command options: `EdgeTol`, `InteriorTol`, `AngleTol`, `NoAutoSort`.
- Its rules are worth copying as validation messages:
  - Open and closed curves cannot be mixed in one direction.
  - A closed network needs at least 3 curves.
  - Sorting can fail; it then falls back to picking curves one by one.
  - There is a warning above 100 curves.

### 4.3 Loft and Sweep [O doc]
- `CreateFromLoft` does **not** sort curves, fix directions or align seams. The caller must
  (`Curve.DoDirectionsMatch`, `ChangeClosedCurveSeam`).
- Optional start and end points. `StartTangent`/`EndTangent` match a surface edge (`BrepTrim`)
  for G1.
- `LoftType` and an angle tolerance.
- Sweep2: `SweepRebuild` modes (rebuild to N points, or refit to a tolerance), and an option
  to keep height scaling separate from width.

### 4.4 Curve and surface fitting helpers [O doc]
- `Curve.Fit(degree, fitTol, angleTol)`.
  - Unset or ≤ 0 tolerances mean the document tolerances.
  - angleTol 0 smooths every kink; > 0 smooths only kinks smaller than it.
  - Command `FitCrv`, options `FitDegree` and fitting tolerance.
- `Curve.Rebuild(pointCount, degree 1..11, preserveTangents)`.
  - `RebuildCrvNonUniform` options: `MaxPointCount`, `ExtraMidpoints`, `Parameterization`.
  - It reports "Approximate achieved tolerance = %g, Point count = %d". Show the same feedback.
- `Surface.Fit(uDeg, vDeg, tol)` (FitSrf, with ReTrim) and `Surface.Rebuild(uDeg, vDeg, uPts, vPts ≤ 1000)`.
- `NurbsCurve.CreateSubDFriendly(points, interpolate, periodic)`. Uniform cubic, which suits
  SubD lofts; needs ≥ 4 points (≥ 6 if periodic).

---

## 5. Mesh preparation

### 5.1 ReduceMesh [O]
- `ReduceMeshParameters()` defaults: `DesiredPolygonCount=0`, `AllowDistortion=false`,
  **`Accuracy=10`** (1 = fast … 10 = accurate), `NormalizeMeshSize=false`.
  - NormalizeMeshSize scales the mesh into a unit cube during reduction.
  - `LockedComponents` are vertices that must not move or be removed. `FaceTags` are also
    accepted.
- The API doc says `AllowDistortion=false` "only simplifies flat (coplanar) regions" and
  ignores the count.
- Command options: `NewFaceCount`, `ReductionPercentage`, `PlanarOnly`, `Accuracy`,
  `LockMeshPoints` (brush select, `AddAllNaked`).
- Result message: "Reduced from {0} faces to {1} faces ({2} %)".
- **openRetop**: QEM (Garland–Heckbert) with boundary and locked-vertex constraints. A
  "PlanarOnly" mode merges coplanar faces only, so the shape cannot change. Lock naked
  vertices by default for scans.
- Related: `Mesh.CollapseFacesByEdgeLength` (Melax-style collapse), and
  `Collapse/Extract/SelMeshFacesByAspectRatio` / `ByArea`.

### 5.2 MeshRepair, Check and the checks to show
`MeshCheckParameters` lists the defects Rhino reports [O]. Use the same list:
- degenerate faces, including quads with one zero-area half
- invalid n-gons
- naked edges (1 face)
- non-manifold edges (> 2 faces)
- extremely short edges
- bad normals: non-unit, zero-length, or differing greatly from the face normals
- duplicate faces (same vertex positions)
- "random" face normals: adjacent faces with the same edge orientation
- disjoint pieces
- unused vertices
- self-intersecting face pairs

The MeshRepair panel is a wizard over these checks. The messages are counted per category.

### 5.3 Individual repair operations [O doc / strings]

| Operation | Behaviour |
|---|---|
| `FillHoles()` | Chains naked edges into loops and triangulates **every** loop, outer boundary included. `FillHole(edge)` fills one. |
| `FillMeshHole`, `FillMeshHoles` commands | Pick one boundary edge, or fill all |
| `HealNakedEdges(d)` | First snaps naked vertices to neighbouring vertices within d. Then splits edges whose closest point lies within d, and zips. ShrinkWrap uses d = 100 × abs tolerance |
| `UnifyNormals()` | Re-winds faces consistently; vertex normals are not recomputed |
| `ExtractNonManifoldEdges(hangingOnly)` | Command `ExtractNonManifoldMeshEdges`, options `MinimumFaceCount`, `ExtractHangingFacesOnly` |
| `AlignVertices` | `Distance`, `OnlyNakeds`, `SelectNakedEdges`, `UseNewMethod`, `Average` |
| `MatchMeshEdge` | Moves naked vertices onto another naked edge; `Ratchet` mode, `Join`, `PickEdges` |
| `CullDegenerateMeshFaces`, `SplitDisjointMesh` | As named |
| `MergeCoplanarFaces` | With `DistanceToMove` |
| `SwapMeshEdge`, `SplitMeshEdge`, `Merge2MeshFaces` | Topology editing |
| `OffsetMesh` | Options: `UseVertexNormals` / `AverageNormals` / user direction, `BothSides`, `Solid`, `AllowDisjoint`, `FlipAll`, `RealtimePreview`, `DeleteInput`. API `Mesh.Offset(d, solidify, direction)` returns the wall faces |
| `Mesh.Smooth(factor, iterations, x, y, z, fixBoundary, coordSystem)` | Uniform (umbrella) Laplacian; per-axis masks; local subsets by vertex index |
| `MeshPatch` | Triangulates closed polylines plus points: outer boundary, holes, `StartingSurface` to pull onto, `TrimBack`. API `Mesh.CreatePatch(...)` |
| `MeshFromPoints` | Modes `OrderedPointGrid` / `UnorderedPoints`. Detects grids automatically; unordered uses 2.5D Delaunay ("Reached maximum recursion limit") |

---

## 6. Region selection and segmentation helpers

- **ExtractMeshPart / SelMeshPart / ExtractConnectedMeshFaces** [O strings]. Grow from a face
  by **angle between neighbouring face normals**.
  - Options: `LessThan`, `GreaterThan`, `AngleBetween`, `BorderOnly`, `MakeCopy`,
    `WholeDisjointParts`, `JoinOutput`.
  - This is the "smart select" of S-05. openRetop already does the same with region grow by
    normal angle.
- **By draft angle**: `ExtractMeshFacesByDraftAngle` with `StartDraftAngleInDegrees`,
  `EndDraftAngleInDegrees` and `ViewNormal`. Selects faces whose normal-to-pull-direction angle
  is in a range. Cheap and useful for picking walls or tops on aligned scans.
- **By aspect ratio and by area**: selection, extraction and collapse variants.
- **Crease analysis**. `MeshCommands.rhp` has a crease-analysis visual mode that colours
  automatically detected crease edge groups from a fixed palette. This shows
  Rhino's automatic crease detection; in QuadRemesh it feeds `DetectHardEdges`.
- `CreaseAngle.rhp` is a small separate plug-in [O].

---

## 7. Curves on the scan

- `Curve.PullToMesh(mesh, tol[, loose])`.
  - Polyline approximation, then closest point on the mesh per sample, joined.
  - `loose=true` (8.17) pulls only the edit points and keeps the curve's structure. It fails
    if any point misses.
- `Curve.ProjectToMesh(curve, mesh, direction, tol)`.
- `Mesh.CreateContourCurves(mesh, plane, tol)` and `(mesh, p0, p1, interval, tol)`.
  - The docs warn that good tolerances are around 1e-7 (`SqrtEpsilon × 10`), not the model
    tolerance.
  - This is what openRetop's Section tool does.
- `Mesh.Split(plane)`, `Split(meshes, tol, splitAtCoplanar, createNgons, ...)`.
  - The doc says the intersection tolerance should be 1e-8..1e-4, i.e. the document
    tolerance reduced by a few orders of magnitude.
- `NewMeshSplitWithCurve` (`MeshCommands.rhp`) splits a mesh along curves pulled onto it, as a
  background task ("Mesh partition in progress").

---

## 8. Analysis and verification

- **PointDeviation** (core) options [O]: `MinRange`, `MaxRange`, `MinRadius`, `MaxRadius`.
  The report reads:
  - "… Analyzed %u points in %u objects."
  - "%u%% are at or below minimum distance (%u points)."
  - "%u%% are between minimum and maximum distances."
  - "%u%% are above maximum distance."

  Copy this three-band (good / warning / out of tolerance) report for S-10 and RE-09.
- **CurvatureAnalysis** (false-colour Gaussian, mean, min and max radius, with `MinRange` and
  `MaxRange`), **Zebra**, **EMap**, **DraftAngleAnalysis**, **ShowEdges** (counts naked and
  non-manifold edges). All are visual analysis modes drawn as vertex colours on a display
  mesh. MeshCommands' crease mode uses the same `VisualAnalysisMode` mechanism.
- `Plane.FitPlaneToPoints(points, out plane, out maxDeviation)` returns the farthest point
  distance. Report it next to the RMS.

---

## 9. Design patterns worth copying

1. **Heavy geometry runs out of process**, as with QuadRemesh, and is cancellable at stage
   boundaries, as with ShrinkWrap's interrupter. Progress is a polled float. openRetop's S-03
   worker matches this already.
2. **Recentre before voxelizing or computing.** ShrinkWrap moves the input's bounding-box
   centre to the origin before working in float32.
3. **Parameters expressed in model units** (voxel = target edge length). Defaults are scaled
   from the document tolerance where it matters: the QuadRemesh edge length is clamped to at
   least the absolute tolerance; ShrinkWrap heal distance = 100 × the tolerance.
4. **Guard against huge jobs** before running them. ShrinkWrap estimates voxel memory and
   warns at 8 GiB.
5. **Every tool has a scripted form with the same options as its dialog.** All commands above
   expose `-Command` options that mirror the panel. This is a useful model for openRetop's
   tests and macros.
6. **Preview, then Apply**: a display conduit draws the result, with "hide input" and "delete
   input" toggles. Both plug-ins do this.

---

## 10. What is not known (open questions)

| Question | Why it is open | How to settle it |
|---|---|---|
| Default `SurfacePull`, and the NetworkSrf tolerance defaults | Patch's main defaults are now known (4.1); these two are not | Read them from Rhino's `-Patch` (with a starting surface) and `-NetworkSrf` prompts |
| ReduceMesh algorithm details (error metric, how Accuracy maps to iterations) | Not documented | Black-box tests: reduce known meshes and compare |
| QuadRemesh internal algorithm | Proprietary engine; only its interface was studied | Do not pursue. Use Instant Meshes or QuadWild (2.4) |
| EXO mesh file format | Not needed for a reimplementation | n/a |
| `GuideCurveInfluence` 1 = ring or loop | The two docs disagree | Check in the Rhino UI |
| Meaning of `relaxDisorientedTriangles = true` in the result | Standard OpenVDB flag | See the OpenVDB `volumeToMesh` docs |
