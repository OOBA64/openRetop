# Reverse-engineering plan: from scan to CAD-ready solid

Owner direction (2026-10-07): "Make what is basically an ExModel / QuickSurface Pro copy in terms
of tooling and workflow ... top priority. The tools can't produce any real CAD-ready surface
geometry. I need this to be transformed into a solid reverse engineering program; the other
stuff can come later."

This plan replaces UX polish as the main track. Track U/D items continue only where a
reverse-engineering task needs them.

## 1. Where we are (audited 2026-10-07)

| Area | Today | Gap to a reverse-engineering tool |
|---|---|---|
| CAD kernel | OpenCASCADE via OCP and CadQuery 2.8 are installed. Used for two things: a planar face from a closed curve, and a loft between two curves. STEP export works. | No primitives, no solids, no booleans, trim, fillet or sewing. Shapes live only as runtime objects: nothing records how they were made, so nothing can be edited or re-saved. |
| Fitting | Least-squares plane through a region. | No cylinder, cone, sphere or torus fit, and no constraints (parallel, coaxial, round to a value). |
| Mesh analysis | Spatial index for closest points; region grow by normal angle. | No curvature, no automatic segmentation into features, no brush selection. |
| Sections | Plane cuts give polylines. | Polylines never become sketch geometry (lines, arcs). Nothing to extrude or revolve. |
| Surfaces | Coons/loft *previews* (triangle meshes) and a two-curve OCC loft. | No B-spline surface fitted to the scan, no deviation control, no continuity between patches. |
| Verification | A point-sampling deviation helper. | No colour map, no report, no tolerance pass/fail. |
| Workflow | Tools are independent commands. | No feature tree, no "edit and rebuild", no alignment step, no guided path from scan to solid. |

Bottom line: the app can look at a scan and draw on it, but it cannot yet make a part.

## 2. Target workflow (what QuickSurface and ExModel do, and what we will do)

```
 Prepare        Segment         Model                          Verify        Export
 --------       ---------       ------------------------       ---------     ------
 Import    ->   Curvature  ->   A. Primitives (plane, cyl,  -> Deviation  -> STEP solid
 Clean          Auto-regions       cone, sphere, torus)        colour map    (and IGES
 Align to       Brush / grow    B. Sketch on section ->        Tolerance     surfaces)
 world axes     Merge / split      extrude / revolve           report
                                C. Freeform B-spline patch
                                Combine: trim, boolean,
                                fillet, sew -> solid
```

Every modelling step is a **feature** in a tree, as in QuickSurface. It stores its inputs and
parameters, such as a region, a sketch, an extrude distance or a constraint. The tree rebuilds
the solid from those. Editing a feature re-runs everything after it. The project file saves
the tree, not shapes.

Three ways to model, because real parts mix them:

- **Primitives** (QuickSurface "fit primitive"): select a region and get an exact plane,
  cylinder, cone, sphere or torus. Constraints snap them square and round, for example "axis
  parallel to Z" or "diameter 12.000". Neighbouring primitives intersect and trim into a solid.
  This covers most machined parts.
- **Sketch** (QuickSurface "2D sketch", ExModel "section sketch"): a section of the scan gives
  points on a plane. Auto-fit turns them into lines and arcs that join tangentially. You edit
  them with constraints (horizontal, tangent, radius) and dimensions, then extrude or revolve
  to a solid ("up to the scan" is an extent option). This covers prismatic and turned parts.
- **Freeform** (QuickSurface "freeform", ExModel "NURBS patch"): select a region and set its
  four boundary curves. A B-spline surface is fitted to the scan points within a tolerance,
  with a control-net density you set and a live deviation map. Adjacent patches meet with
  tangency (G1). This covers castings, ergonomic and styled shapes.

## 2a. Reference workflow: ExModel on a car fender (video reviewed 2026-10-08)

The owner pointed at a one-minute ExModel Pro demo (3DWonders, "Transform a car fender scan
into a CAD model") as the target. What it does, step by step:

1. **3D Sketch** on the mesh: splines drawn on the scan ("pick points through mesh", snap on,
   mesh shown offset so the curves stay visible), along the wheel-arch flange edges.
2. **Loft** between two sketch curves gives the flange strip.
3. **Fit Surface**: brush or smart-select an area of the scan (angle tolerance, "select all
   connected"), choose the type (freeform, plane, cylinder, cone, sphere, torus, ...), set U x V
   control points, method, smoothness and "expand by", Fit, then Create. The result is an
   untrimmed patch larger than the selection.
4. More sketch curves along the character lines; **Extend** surfaces past their edges.
5. **Fill Surface** inside a closed chain of edges and curves, each side Contact (G0) or Smooth
   (G1), optionally pulled onto the scan ("on scan data").
6. **Trim**: automatic trimming of all the surfaces against each other, with a tolerance and an
   "overlap with reference mesh" setting; pieces shown in different colours; click to keep or
   drop ("single surface" / "multiple surfaces"); OK sews them.
7. **Compare**: deviation colour map of the scan against the surfaces.
8. Export (IGES/STEP).

Lessons for us: the core of the product is a small set of *surface* tools that each produce a
real OCC face, plus mutual trimming. Every tool is a panel with a few parameters and an
immediate preview. The patches are deliberately oversized and trimmed at the end. This is
milestone **S** below, which now comes before the rest of M1.

## 2b. Reference workflow 2: ExModel on a motorcycle swing arm (video reviewed 2026-10-08)

The owner's second reference (3DWonders, "Rebuilding a Swing Arm | EXModel Pro"): a cast,
very organic part rebuilt quickly with *solid* tools on top of the surfacing ones.

1. **Create Sketch** on a plane (XY/YZ/XZ, a CAD face, an offset, or placed interactively;
   "for extruded" or "for revolved" surface). The scan's **section** at the plane is drawn on
   the sketch as reference (optionally stacked sections or the outline of the whole scan).
2. **Fit primitives** on the section: brush over the section points and a line, arc, circle,
   rectangle, slot or spline is fitted at once within a target tolerance ("instant fit");
   lines within a few degrees of horizontal/vertical are made exact; corners can be joined
   with a radius ("instant join").
3. **Extrude** the profile: one- or two-sided depths, draft, inverse, new solid / add / cut;
   top and bottom depths dragged with handles in the viewport; live **deviation analysis**
   on the scan near the new walls while adjusting.
4. **Fillet** the edges between faces: pick an edge (tangent edges added), constant or
   start-to-end radius, an **Auto** button that measures the radius from the scan, and live
   analysis of the fillet against the scan. Used constantly.
5. **Extract primitives**: brush an area, get a plane or cylinder (also line, cone, sphere)
   patch sized to the area, with corner/edge **handles to resize** it by dragging.
6. Fit Surface for the freeform sides, **Trim** everything into a solid body, Compare.

What it adds to section 2a: sketches from sections with fitted lines and arcs, extrude/revolve
to solids, fillets measured from the scan, resizable primitive patches, and live deviation in
every tool. These are milestone M2 (RE-11..16), now pulled forward as S-13..S-17.

## 3. How we will know it works: round-trip benchmarks

Every milestone is measured against known CAD, not against "looks right". A benchmark suite
generates reference parts with CadQuery and turns each into a scan-like mesh:

1. Tessellate the part.
2. Add measured noise (0.01 to 0.05 mm, the level of a good structured-light scanner).
3. Add random holes and an uneven triangle density.

Then the tools reverse-engineer each one, and we compare the result with the original. Each
benchmark is an automated test with numeric acceptance (for example "cylinder diameter within
0.01 mm, axis within 0.05 degrees"). There are also live runs through the real UI.

| Benchmark | Shape | Exercises |
|---|---|---|
| B1 bracket | plate + boss + 2 holes + chamfer | planes, cylinders, trim, boolean |
| B2 shaft | turned profile with grooves and a cone | section sketch, revolve, cone fit |
| B3 housing | pocketed block, drafted walls, fillets | sketch + extrude to scan, draft, fillets |
| B4 knob | revolved base + freeform grip | freeform patch, G1 to a primitive |
| B5 casting | multi-patch freeform with primitives | patch network, trim, deviation report |

## 4. Milestones

### S - The surfacing toolset in the app (first, since 2026-10-08)
The ExModel workflow of section 2a, usable from the UI. Kernel first, then each tool as a
panel with preview, in the order the video uses them.

| ID | Task | Acceptance |
|---|---|---|
| S-01 | Fit Surface kernel: freeform B-spline fit to a scan area (plane or conformal parameterization, smoothing, expand, parameter correction) and the exact types (plane, cylinder, cone, sphere, torus) as faces | B4 grip sector: within 0.02 mm RMS of the CAD with a 16 x 16 net; the expand margin stays near the natural continuation; under 1 s. |
| S-02 | Surfacing kernel: loft, fill (G0/G1 sides, on scan data), extend (G1), split everything by everything and keep the pieces on the scan, sew into a shell or solid, signed deviation | B1 trims and sews into one valid solid within 0.2% volume; fill on a known surface within 0.01 mm; fill tangent to a smooth neighbour within 1 degree. |
| S-03 | Kernel worker: every kernel operation runs in a separate process with a timeout; a crash or hang returns a failure and the app carries on | A deliberately crashing and a hanging operation each report an error; the next operation succeeds. |
| S-04 | Model document: the surfaces and bodies made by the tools, each with the inputs and parameters that built it, shown in the tree and viewport, saved in the project | Reopening a project shows the same surfaces; undo/redo per tool. |
| S-05 | Scan area selection: smart select (grow by angle), brush add/erase, select connected, clear; highlighted on the scan | Brush follows the pointer on a 1M-triangle scan without lag. |
| S-06 | Fit Surface tool: panel with the selection tools, type buttons, U/V, smoothness, expand, Fit (preview with deviation), Create | On B4, a user fits the grip patch in under a minute. |
| S-07 | 3D Sketch and Loft: the curve tool draws B-spline curves on the scan; Loft between two or more curves | Fender-style flange strip from two curves. |
| S-08 | Fill Surface tool: pick a closed chain of curves and surface edges, Contact/Smooth per side, on scan data | Fills a four-sided gap between fitted patches with G1 sides. |
| S-09 | Extend and Trim tools: extend by a distance; automatic trimming (tolerance, overlap), click pieces to keep or drop, OK sews; a closed result becomes a solid | B1 from fitted patches to a solid entirely in the UI. |
| S-10 | Compare: deviation colour map of the scan against the model, legend and statistics | Updates in about a second on a 1M-triangle scan. |
| S-11 | Export the model: STEP (solids and surfaces) and IGES (surfaces), checked by re-import | Re-import gives the same faces and volume. |
| S-12 | Save the model (surfaces, bodies, 3D Sketch) in the project file | Reopening a project shows the same surfaces and curves; undo history starts fresh. |
| S-13 | Section sketch: sketch plane (world planes, a model face, offset, interactive), the scan's section drawn on it, brush-to-fit line/arc/circle/spline within a tolerance, horizontal/vertical snapping, corner radii, drag endpoints; closed profiles detected | B2 shaft profile and B3 housing outline fitted to 0.02 mm, every line and arc found. |
| S-14 | Extrude and revolve a sketch profile: one/two-sided depth, draft, new body / add / cut; depth handles in the viewport; live deviation | B3 housing walls and pocket within 0.05 mm of the CAD; B2 shaft revolved within 0.02 mm. |
| S-15 | Fillet and chamfer solid edges: pick edges (tangent chain), constant or variable radius, Auto radius measured from the scan, live deviation | B3 R3/R2 fillets found within 0.05 mm by Auto. |
| S-16 | Primitive patches sized to their area automatically, with handles to resize planes (edges, corners) and cylinders (length, arc) | A plane patch dragged larger keeps its fit; Trim uses the new size. |
| S-17 | Live deviation analysis in every tool panel (tolerance, colour map near the new geometry) | Updates while dragging a depth or radius. |

### M1 - Machined parts from primitives (B1)
The first thing that produces a real, exportable solid.

| ID | Task | Acceptance |
|---|---|---|
| RE-01 | Benchmark harness: CadQuery reference parts to noisy scan meshes, and a `measure_against_reference` helper | B1 to B5 generate deterministically. Noise and holes are seeded. Ground-truth parameters are stored with each part. |
| RE-02 | Per-vertex curvature (principal curvatures from local quadric fits, Numba) and a curvature colour map in the viewport | Measured error under 2% on sphere and cylinder benchmarks. Under 1 s for 1M vertices. Toggle in View. |
| RE-03 | Automatic segmentation: region growing on normal and curvature continuity, with each region classified as plane, cylinder, cone, sphere, torus or freeform; shown as coloured regions | B1 splits into its true faces (at least 90% of triangles correct). Each region has a class and a fit error. |
| RE-04 | Region editing: brush select (add/subtract), grow and shrink, merge and split. Multiple regions (replaces the single active region) | Live brush at 60 fps on 1M triangles. Undo per stroke. |
| RE-05 | Primitive fitting library: plane, sphere, cylinder, cone and torus by robust least squares (good initial guess, Gauss-Newton or Levenberg-Marquardt, trimmed outliers); quality report | On B1/B2 noise: radius error under 0.01 mm, axis error under 0.05 degrees. Never crashes on degenerate input (returns a reason). |
| RE-06 | Constraints and snapping: axis parallel or perpendicular to world or to another primitive, coaxial, concentric, round values (0.01, 0.1, 0.5, 1 mm, or fractions of an inch) | Each constraint keeps the fit as close as possible to the data while honouring the rule (constrained least squares). Shown as badges on the primitive. |
| RE-07 | Feature tree v1: Primitive feature (region + type + constraints to an OCC surface); tree panel with rename, suppress, delete, and edit-and-rebuild; saved in the project (schema v3) | Reopening a project rebuilds identical geometry. Undo/redo covers feature edits. |
| RE-08 | Primitive to solid: intersect neighbouring primitives (half-space booleans of a bounding block, or face trimming by intersection curves) and sew into a closed solid | B1 becomes one valid closed solid (BRepCheck). Volume within 0.5% of the reference. |
| RE-09 | Deviation analysis: distances from scan vertices to the solid or faces, as a colour map with a legend and tolerance band, plus a report (max, mean, % in tolerance) | B1 at 0.02 mm noise: 99% of vertices within 0.05 mm. Map updates in under 1 s. |
| RE-10 | Export: STEP AP214 of solids with units and names, IGES of surfaces; checked by re-import | Re-imported B1 has the same volume and face count. |

### M2 - Sketch, extrude and revolve (B2, B3)

| ID | Task | Acceptance |
|---|---|---|
| RE-11 | Sketch plane from a section plane or a primitive face; the scan's section shown in the sketch as reference points | The sketch opens looking straight at the plane, with the section points visible. |
| RE-12 | Auto-fit section to sketch: split the polyline at curvature changes and fit lines and arcs within a tolerance, joining them tangentially where the data is smooth | B2 profile: every line and arc found, radii within 0.01 mm, no spurious tiny segments. |
| RE-13 | Sketch editing: drag endpoints and arcs, add and delete entities, trim and extend | Interactive at 60 fps. Undo per edit. |
| RE-14 | 2D constraint solver (coincident, horizontal, vertical, parallel, perpendicular, tangent, equal, radius, distance, angle) using damped least squares; DOF status shown | Standard sketches solve in under 20 ms. Conflicts reported, never silently dropped. |
| RE-15 | Extrude (distance, symmetric, to a face, "up to scan") and revolve (axis from a sketch line or a fitted cylinder); new body, add or cut | B2 revolves within 0.02 mm deviation. B3 pockets cut correctly. |
| RE-16 | Fillet, chamfer and draft features on solid edges, with the radius suggested from the scan (fit a cylinder to the fillet strip) | B3 fillets found and applied, radius within 0.05 mm. |

### M3 - Freeform surfaces (B4, B5)

| ID | Task | Acceptance |
|---|---|---|
| RE-17 | Freeform patch: region + 4 boundary curves (drawn, or taken from region edges) to a least-squares B-spline surface (U x V control net, smoothing term, boundary interpolation); OCC Geom_BSplineSurface face | B4 grip at 0.02 mm noise: max deviation under 0.05 mm with a 12 x 12 net. Fitting under 1 s. |
| RE-18 | Patch controls: net density, smoothness slider, live deviation map while adjusting | Updates in under 200 ms for a 12 x 12 net on 200k points. |
| RE-19 | Patch networks: shared boundaries, G1 across them (tangent-plane constraint in the fit), and G1 to primitives | B5: no visible creases. Measured normal discontinuity under 0.5 degrees along joins. |
| RE-20 | Trim and sew freeform with primitives into a solid | B4 becomes one closed solid. |
| RE-21 | Existing tools re-homed: manual curves become patch boundaries and sketch references; the two-curve loft becomes a real loft feature; the four-boundary fill becomes a freeform patch with no region (pure boundary) | No dead-end tools left. |

### M4 - Workflow and productivity

| ID | Task | Acceptance |
|---|---|---|
| RE-22 | Alignment: pick a plane, axis and origin (from primitives) to align the scan to world XYZ; 3-2-1 and best-fit options | B1 delivered tilted becomes square to the world axes within 0.01 degrees. |
| RE-23 | Mesh preparation: hole fill, decimate (feature-preserving), remove islands, smooth (optional, non-destructive) | Before/after deviation reported. |
| RE-24 | Workflow stepper (replaces UX-10): Prepare, Segment, Model, Verify, Export, with each step's tools, "what's next", and status | A new user takes B1 from scan to STEP following only the stepper (usability script). |
| RE-25 | Auto-model suggestions: after segmentation, offer "make primitives for all planar/cylindrical regions" in one step | B1 from scan to solid in under 2 minutes of user time. |
| RE-26 | Performance budget: every interactive tool at 60 fps on a 1M-triangle scan; heavy operations off the UI thread with progress | Benchmarked in CI on a fixed machine profile. |

## 5. Architecture decisions

- **Feature tree, not shapes.** A `Feature` holds its inputs (region ids, sketch entities,
  parameters, constraints) and builds an OCC shape on demand. The project saves features.
  Rebuild order is the tree order. Each feature caches its shape by input hash. This is the
  core QuickSurface and ExModel behaviour: everything stays editable.
- **The kernel stays behind `cad_kernel`.** New operations (primitive faces, extrude, revolve,
  boolean, fillet, sew, B-spline surface, STEP/IGES) go through one OCP adapter. The rest of
  the app never imports OCP directly, so tests can run without it where possible.
- **Numerics in plain NumPy/SciPy, hot loops in Numba.** These are the fitting, curvature,
  segmentation and brush code. Each has pure functions with their own tests.
- **Regions become a collection** of face-sets on the source mesh. Multiple regions, stable
  ids, saved with the project. The single "active region" goes away.
- **Display stays fast.** Shapes are tessellated once per rebuild for display, and picking
  uses the spatial-index path from the performance fix.

## 6. Order of work

M1 first, in ID order. RE-01 (benchmarks) comes first so every later task has a number to hit.
At the end of each milestone there is a live demo on its benchmarks, and a short report with
numbers before moving on. M1 is the biggest jump in usefulness, because it produces the
first real solid.
