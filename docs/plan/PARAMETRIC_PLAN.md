# Parametric modelling plan: a Fusion 360-style Solid workspace on top of the scan

Owner direction (2026-10-09): "plan for some sort of traditional sketching/modeling system that
will allow a fusion 360 like solid modeling workflow, it would be nice to have this to make
edits to reversed geometry. This can be completed whenever."

## 1. Why, and where it fits

Reverse engineering gives a part's *shape*. A usable CAD part also needs *intent*: a hole is
Ø8.00 not Ø7.98, two walls are parallel, the boss is centred, the fillet is R3 everywhere.
And the part usually gets changed afterwards (a longer flange, an extra mounting hole). That
is what a parametric history modeller is for. The scan stays in the picture as a reference:
sketches are drawn over its sections, dimensions snap to measured values, and a live
deviation map shows where the design and the scan disagree.

Workspaces after this plan:

| Workspace | Purpose |
|---|---|
| Scan | Import, clean up, align, sections, regions, measure |
| Surface | Organic shapes: curves on the scan, fitted surfaces, trim and sew (ExModel style) |
| Solid | History-based parts: constrained sketches, features, a timeline (Fusion style) |

Bodies made in Surface (a sewn solid, a fitted patch) enter Solid as *base features* and can be
edited there with direct operations (press/pull a face, fillet an edge, cut a hole).

## 2. The model

```
Design
 ├── Parameters        user parameters (name = expression, units), referenced by any value
 ├── Origin            world planes XY/XZ/YZ, axes, origin point
 └── Timeline          ordered features; each produces or changes bodies
      ├── Base feature        a body imported or built in Surface (no history inside)
      ├── Sketch              on a plane / a face / an offset or section plane
      ├── Construction        offset plane, plane at angle, midplane, axis through points
      ├── Extrude / Revolve / Sweep / Loft (solid)
      ├── Fillet / Chamfer / Shell / Draft / Hole
      ├── Mirror / Pattern (linear, circular)
      ├── Combine (join, cut, intersect) / Split
      └── Direct edits        press/pull face, move face, delete face, replace face
```

- **Features** are plain data (inputs, parameters, references) and are *regenerated* by the
  kernel worker (OpenCASCADE). The design keeps each feature's resulting BREP, so an edit
  regenerates only from the changed feature on. A failed feature is marked red in the
  timeline with the kernel's reason; the features after it are skipped, not lost.
- **References** to geometry (an edge to fillet, a face to sketch on) are stable names: the
  feature that made the face plus the sketch entity or side that produced it (the topological
  naming problem). Fallback when a name no longer resolves: the nearest face/edge of the same
  type to where the old one was, flagged for the user to check.
- **The timeline** has a roll-back marker: drag it back to see / edit the part as it was;
  features after it are suppressed until it moves forward again.

## 3. Sketches

- **Planes**: world planes, a planar model face, offset / angled construction planes, and a
  *scan section plane* (the scan's cut is shown as reference geometry in the sketch).
- **Entities**: point, line, arc (3-point, centre, tangent), circle, ellipse, rectangle,
  slot, polygon, fit-point spline; construction toggle; trim / extend / offset / fillet in
  the sketch.
- **Constraints**: coincident, horizontal, vertical, parallel, perpendicular, tangent, equal,
  concentric, midpoint, symmetric, collinear, fix. **Dimensions**: distance, angle, radius /
  diameter, driving or driven, values or expressions of parameters.
- **Solver**: our own, on SciPy `least_squares` (BSD; SolveSpace's solver is GPL): residuals
  per constraint, Levenberg-Marquardt from the current positions (so a drag moves the least),
  degrees of freedom from the Jacobian's rank: entities turn from blue (free) to black (fully
  defined) as in Fusion; over-constraint reported by the conflicting constraints.
- **From the scan**: *Fit from Section* (what Section Sketch does now) produces real sketch
  entities **with constraints already applied**: coincident ends, tangent fillets, H/V lines,
  equal radii where radii agree within the tolerance. *Snap dimensions*: a typed dimension can
  be compared against the measured value, and "round to" (0.5 mm, 0.1 mm) offered.
- **Profiles**: closed regions of the sketch (with islands) are found automatically and picked
  by clicking inside them, for extrude / revolve.

## 4. The reverse-engineering link

- Live deviation in every feature dialog: how far the result is from the scan, and a colour
  map while the dialog is open.
- Auto values from the scan: extrude "to scan" (depth measured, as today), fillet "auto
  radius" (radius fitted to the scan along the edge), hole diameter from a fitted cylinder,
  draft angle from the fitted wall.
- Base features from Surface keep a link back to their fit, so they can be refitted.

## 5. Milestones

| ID | Item | Acceptance |
|---|---|---|
| P-01 | Feature/timeline data model, regeneration in the worker, save/load | Extrude of today's sketch replays from the saved file to the same volume; an edit to an early feature regenerates the rest |
| P-02 | Constraint solver (points, lines, arcs, circles; 12 constraints; dimensions) | Rectangle with H/V/equal/distance constraints solves fully defined; DOF count right on 20 test sketches; a drag moves only free geometry |
| P-03 | Sketch mode UI: draw tools, constraint glyphs, inline dimensions, colour by DOF | Draw a plate with 4 holes, fully define it, change a dimension, the part follows |
| P-04 | Profiles: regions found from sketch curves (with islands), picked by click | Nested and touching profiles picked correctly on 10 test sketches |
| P-05 | Extrude / Revolve as features (new, join, cut, intersect; distance, to object, symmetric, taper) | B2 shaft revolved from a section; B3 housing from one sketch + one cut |
| P-06 | Fillet / Chamfer (constant, variable, auto radius from the scan) | B3 housing edges filleted with radii found within 0.1 mm of the truth |
| P-07 | Timeline UI: roll-back marker, edit, suppress, reorder, failure display | Roll back, insert a feature, roll forward: the part rebuilds |
| P-08 | Construction geometry: offset/angled/midplane planes, axes, points | Sketch on an offset plane and on a model face |
| P-09 | Fit from Section becomes constrained sketches | B3 section: fully defined except position, radii equal where equal |
| P-10 | Parameters and expressions | `wall = 2 mm` drives three features |
| P-11 | Shell, Draft, Hole, Mirror, Pattern | A shelled, drafted housing with a patterned boss |
| P-12 | Direct edits on base features: press/pull, move, delete, replace face | A sewn Surface body gets its flange lengthened by 10 mm |
| P-13 | Live deviation in feature dialogs | Every feature dialog shows deviation before Create |
| P-14 | Topological naming robustness | A fillet survives an upstream sketch dimension change on B3 |

Status (2026-10-09): **P-02 done** (`modeling.sketch2d`: the solver, 12 constraints, 6 dimensions,
DOF and fully-defined; no UI yet). **P-01 done** for sketches and extrudes (`modeling.timeline`,
`application.regeneration`; History in the scene tree, extrude inputs editable in Properties).
Next: P-03 / P-04 / P-05, i.e. sketch mode on top of the solver and extrude from its profiles.

Order: P-01 and P-02 first (everything stands on them), then P-03/P-04/P-05 together (the
first end-to-end Fusion-style loop), then P-06, P-07, then the rest as needed by real parts.

## 6. What exists already and becomes part of this

- Section Sketch (lines and arcs fitted to a section, hand editing) -> P-09's starting point.
- Extrude with depth from the scan -> P-05's "to scan" extent.
- Profile wires and faces (`cad_kernel.profiles`), extrude with per-loop depths
  (`cad_kernel.features`) -> the regeneration code of P-05.
- Workspaces -> the Solid workspace hosts sketch mode and the timeline.
