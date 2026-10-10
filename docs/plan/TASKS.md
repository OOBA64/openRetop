# openRetop task list

Owner of the plan: the `claude/openretop-refactor-b59181` line of work.
Supersedes the numbered Codex task files in `docs/v3/tasks/` (kept as history).

Conventions
- **Priority:** P0 do first, P1 next, P2 when convenient.
- **Size:** S under a day, M a few days, L a week or more.
- **Status:** `todo`, `doing`, `done`. A task is done only when its acceptance
  criteria pass in an automated test **and** it was checked in the running app.
- Every task lands as small commits; the full suite, `ruff` and `mypy` stay green.
- Evidence for UX tasks is in [UX_AUDIT.md](UX_AUDIT.md); the reasoning for the R-tasks is in
  [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md).

## Completed in the first rework pass

| ID | Summary |
|---|---|
| D-01 | STL vertices welded at load (tolerance scaled to mesh); box face = 2 triangles |
| D-02 | Loader: ordinary exceptions, honest normals flag; adjacency cache on the mesh |
| D-03 | Atomic project/settings writes, relative mesh path, schema v2 + migrations, region round-trip |
| D-04 | Section curves fitted with tolerance-driven B-splines; CAD builds NURBS edges/lofts; seam alignment |
| D-05 | Units (mm/cm/m/in) at import, in the project, driving tolerances and STEP header |
| D-06 | Vectorised sections/adjacency/normals; worker-thread import, sections and CAD builds |
| D-07 | `openretop` src-layout package, pyproject, ruff, mypy, CI rewrite, feature-named tests |

---

## Track RE - reverse engineering (TOP PRIORITY since 2026-10-07)

Scan to CAD-ready solid, QuickSurface / ExModel style: segment, fit primitives, sketch and
extrude/revolve, freeform B-spline patches, trim and sew into a solid, deviation check, STEP.
Full plan, benchmarks and acceptance criteria: [RE_PLAN.md](RE_PLAN.md). Status of each RE
task is tracked here.

Since 2026-10-08 milestone **S** (the ExModel surfacing toolset in the app, from the
reference video in RE_PLAN section 2a) comes first.

| ID | Milestone | Status | Task |
|---|---|---|---|
| S-01 | S | done | Fit Surface kernel (`fitting.bspline_surface`: plane/conformal parameterization, smoothed least squares stiffened where no data reaches, parameter correction, expand, auto net; exact types via `fitting.primitives`): B4 grip sector within 0.02 mm RMS of the CAD (16 x 16 net), 0.1-0.3 s |
| S-02 | S | done | Surfacing kernel (`cad_kernel.surfacing`): loft, fill (G0/G1, on scan), extend (G1), split-all + keep pieces on the scan, sew to shell/solid, signed deviation; B1 trims and sews into a valid solid within 0.02% volume |
| S-03 | S | done | Kernel worker process (`cad_kernel.worker` + plain-data jobs in `cad_kernel.jobs`): a crash or a hang (timeout) returns a failure and the next job starts a fresh worker |
| S-04 | S | done | Model document (`modeling.document`): surfaces and bodies with their BREP, display mesh, edges, build inputs and fit stats; Model group in the tree (show/hide, rename, select, delete), coloured in the viewport, inspector stats, undo/redo per tool. Todo: saved in the project file |
| S-05 | S | done | Scan area selection (`modeling.scan_selection`): Smart (grow until neighbours turn more than the angle), Brush and Erase (drag; left button owned by the tool, Alt+drag rotates), whole connected piece, Clear, Invert; orange overlay; picks go through fitted surfaces to the scan |
| S-06 | S | done | Fit Surface panel: selection tools, type (Auto, Freeform, Plane, Cylinder, Cone, Sphere, Torus), U x V (Auto), smoothness, expand, tolerance, Fit preview with deviation, Create (Enter) |
| S-07 | S | done | 3D Sketch (`modeling.sketch`, Surfacing toolbar): click points on the scan; curves pass exactly through them and lie on the scan (centripetal Catmull-Rom, samples moved along the blended surface normal: no overshoot, no jumping to another face); clicking an existing point connects (and finishes), the first point closes; drag a point to move it (every curve through it follows); Enter/C/Backspace/Esc; Loft and Face From Curves (a loop of connected curves: B-spline fitted to the scan inside, trimmed to the curves). Casting: face 0.035-0.05 mm RMS |
| S-08 | S | doing | Fill panel: click curves and surface edges around a gap (highlighted), Contact/Smooth per side, follow the scan; tested from curves. Todo: verify edge picking with a live session |
| S-09 | S | done | Extend (by a distance, G1) and Trim (automatic: split all, keep pieces on the scan with tolerance/overlap; click pieces to keep/drop; Apply sews; closed = solid). B1 in the real window: one valid solid, volume 0.012% from the CAD. Manual trim: Cut Line across a surface, Enter, click pieces to drop (fixed 2026-10-10: its clicks never registered). Todo: trim open borders to the scan outline |
| S-10 | S | done | Compare: deviation colour map on the scan (green within +/- tolerance, yellow-red above, cyan-blue below, legend), RMS/max/% within; surfaces show as edges while the map is up. B1: RMS 0.020 mm, 98.7% within 0.05 mm |
| S-11 | S | done | Export Model (File, Ctrl+E, Surfacing toolbar): STEP or IGES of the selected or visible model, read back to check the face count |
| S-12 | S | done | Save model surfaces, bodies and the 3D Sketch in the project file (`modeling.persistence`: a `model` key with compressed BREP, display mesh, edges and sketch; older versions carry it through untouched) |
| S-13 | S | doing | Section sketch: plane + scan section, brush-to-fit lines/arcs/circles/splines, H/V snap, corner radii. Done: auto line/arc profile (`modeling/profile2d.py`), Section Sketch tool (world planes + offset, click to place, auto tolerance, exact wire/face), hand editing (U-03). Later: brush-to-fit single primitives, splines, face/offset planes |
| S-14 | S | doing | Extrude / revolve sketch profiles to solids (depth handles, draft, add/cut), live deviation |
| S-15 | S | todo | Fillet / chamfer solid edges with Auto radius from the scan, live deviation |
| S-16 | S | doing | Primitive patches auto-sized, with drag handles to resize. Done: arrows on every side and corner of fitted planes, cylinders, cones, freeform (drag, or click and type a distance). Todo: auto size to the face's footprint (H-03) |
| S-17 | S | todo | Live deviation analysis in every tool panel |
| U-01 | U | done | (User feedback on a real 794k-triangle bumper scan: curves froze the app ~10 s per click, did not follow body lines, could not be edited.) 3D Sketch curves run along the surface (`modeling.surface_paths`: shortest path in a capsule, 30-100 ms), relaxed coarse to fine, smooth through points; Follow body lines (crease map, crest-centred: 1.3 mm off a fender shoulder line from two clicks vs 15 mm plain); Show body lines; edit points/curves (insert, delete, split, open/close, reverse, smoothness), right-click menu; brush ring with [ ] |
| U-02 | U | done | Workspaces: Scan, Surface Modeling, Solid Modeling (tabs; each its own toolbar; tools switch to their workspace; remembered) |
| U-03 | U | done | Section Sketch profiles edited by hand (drag corners, radius, sharp/round corner, H/V, delete segment, close profile; undo in the tool; deviation re-measured); Edit Sketch reopens a created sketch |
| U-04 | U | todo | Retire or fold the older Curve tool (Create menu) into 3D Sketch: two curve systems confuse |
| U-05 | U | todo | Scan workspace: cleanup tools (remove pieces, fill holes, decimate) and alignment to world axes from picked faces |
| U-06 | U | doing | Drag handles in the 3D view for extrude depth and patch size (S-16), not only number fields. Done: patch size. Todo: extrude depth |
| RE-01 | M1 | done | Benchmark harness: CadQuery reference parts to noisy scan meshes (`openretop.benchmarks`: B1 bracket, B2 shaft, B3 housing, B4 knob, B5 casting; truth parameters, per-triangle face labels, seeded noise and holes; measured noise RMS matches sigma) |
| RE-02 | M1 | todo | Per-vertex curvature + curvature colour map |
| RE-03 | M1 | done | Automatic segmentation into classified regions (`openretop.segmentation`: fit-guided region growing with a saturation test; 95-97% of triangles correct on B1-B5, every true face found, 1.5-3 s prismatic / ~8 s freeform; freeform areas still yield some small primitive regions, RE-04 edits them) |
| RE-04 | M1 | todo | Region editing: brush, grow/shrink, merge/split, many regions |
| RE-05 | M1 | done | Primitive fitting: plane, sphere, cylinder, cone, torus (`openretop.fitting`; at 0.02 mm noise: B1 radii within 0.004 mm, axes within 0.02 deg, cone half-angle within 0.02 deg; sphere cap / quarter torus within 0.004 mm; simplest-first classification ~0.2 s; never raises) |
| RE-06 | M1 | todo | Constraints and snapping for primitives |
| RE-07 | M1 | todo | Feature tree v1 (editable, rebuilt, saved) |
| RE-08 | M1 | doing | Primitives to a closed solid (v1 done: `cad_kernel.primitive_solid`, MakerVolume cells classified by the scan; B1 volume within 0.03%, B2 0.05%, B3 0.4% from automatic segmentation; todo: worker-process isolation, tori, speed) |
| RE-09 | M1 | todo | Deviation colour map and report |
| RE-10 | M1 | todo | STEP solid / IGES surface export, verified by re-import |
| RE-11..16 | M2 | todo | Sketch on section, auto-fit lines/arcs, constraints, extrude/revolve, fillets |
| RE-17..21 | M3 | todo | Freeform B-spline patches, G1 networks, trim/sew, re-home existing tools |
| RE-22..26 | M4 | todo | Alignment, mesh prep, workflow stepper, auto-model, performance budget |

## Track H - human use (audit of 2026-10-10)

Every workflow driven through the real window with real mouse and key events
(`scripts/usability`), judged as an experienced Design X / QuickSurface user and as a
newcomer. Evidence, persona verdicts and the bugs fixed during the audit:
[HUMAN_AUDIT.md](HUMAN_AUDIT.md). Order within a priority is the order to do them in.
Each task is checked again with the usability scripts, not only unit tests.

| ID | Pri | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| H-01 | P0 | M | todo | **Align the scan to the world** (Scan workspace): pick fitted or picked features - plane gives a world plane, cylinder or two planes' intersection gives an axis, a point or sphere gives the origin (3-2-1); preview, Apply moves the scan and everything built on it; undo | A tilted bracket scan is square to XY/XZ within 0.05 deg in three clicks; Section Sketch planes then lie on its faces |
| H-02 | P0 | M | todo | **Type In and constraints for fitted primitives** (QuickSurface plane dialog): plane - from another plane at an offset, middle plane of two, normal parallel/perpendicular to a plane or axis; cylinder/cone/sphere - typed radius (round to a value), axis parallel/perpendicular/coaxial; deviation updates live | Bracket: a hole re-typed to 8.00 and its axis made perpendicular to the base; deviation shown before Apply |
| H-03 | P0 | S | todo | **Fitted planes sized and turned to the face**: rectangle along the selection's principal directions with a small margin (not a 1.3x-diagonal square on OCC's axes); fitted surfaces semi-transparent while the Fit tool is open | A 100 x 10 mm face gets a plane about 110 x 20 mm whose sides are parallel to the face's edges |
| H-04 | P0 | M | todo | **Automatic segmentation in the app** (the kernel's RE-03): Scan > Segment colours the scan by region with its type; in Fit Surface a click selects a whole region; Auto prefers an exact type when it fits within tolerance (the oil pan flange chose freeform) | Bracket: every face is one click; oil pan flange fits as a plane |
| H-05 | P0 | M | todo | **Help that answers "how do I"**: F1 and Help > Getting Started (the scan to STEP path in six steps, each a button that starts the tool), Help > Mouse & Keys for the active tool (absorbs UX-17), a "?" in each tool panel opening that tool's page of the user guide | F1 in Trim shows the Trim page; a newcomer reaches Export from Getting Started alone |
| H-06 | P0 | S | todo | **Trim/sew results a person can act on**: show open edges in a bright colour after Apply; message in plain words ("Not closed yet: 3 edges have no neighbour - fit or extend the face next to the highlighted edges") instead of "Shell with N open edges" | Bracket with one face missing: the gap's edges are highlighted and the message names the next action |
| H-07 | P0 | M | todo | **Scan cleanup basics** (part of U-05/R-10): delete selected area / disconnected pieces, fill holes (small ones automatically), decimate to a triangle count, smooth; each undoable | The bumper's stray shells removed and decimated to 300k in under 30 s |
| H-08 | P1 | S | todo | **Autosave and recovery** (UX-19, raised from P1-later): snapshot beside the project every few minutes and before risky operations; offered at start after a crash | Kill the process after fitting three faces: the next start offers them back |
| H-09 | P1 | M | todo | **Menus that match the workspaces** (UX-05): Create = Fit Surface, Surface Sketch, Section Sketch, 3D Sketch, Extrude, Loft, Fill, Face From Curves, Section Plane; Modify = Move/Rotate, Extend, Trim, Edit Feature; locks leave the menus (they are in the transform hint); Edit loses the mesh-specific duplicates; Scan menu for scan-only commands | Every toolbar command is in exactly one menu under the verb a user would guess |
| H-10 | P1 | S | todo | **Three sketch tools explained** (decision for the owner: keep the names and explain, or rename Section Sketch to "Sketch From Section"): each tool's panel starts with one line saying what it makes and when to use the other two; the palette shows that line | A newcomer picks the right tool for "a profile of this flange" in a hallway test |
| H-11 | P1 | S | todo | **Navigation presets**: openRetop (current), SolidWorks/Design X, Fusion 360, Blender mouse mappings in Preferences | Each preset orbits/pans/zooms with its own buttons; setting persists |
| H-12 | P1 | S | todo | **No 10 s wait on the first fit**: start the kernel worker in the background when a scan opens | First Create after opening takes as long as the second |
| H-13 | P1 | S | todo | **Fit Surface guards**: warn when the selection is mostly covered by an existing surface (duplicate); hole picking: a click inside a small hole selects its wall | Clicking an already fitted face says so; a 6 mm hole on the bracket is one click |
| H-14 | P1 | S | todo | **Section Sketch tolerance from the scan's noise**, not its edge length; segments over tolerance drawn red with their deviation | Oil pan section: max deviation shown, no segment over tolerance unmarked |
| H-15 | P1 | L | todo | **Fillet and chamfer** (S-15 / P-06) with the radius measured from the scan | Bracket edges filleted with radii within 0.1 mm of the CAD |
| H-16 | P1 | L | todo | **Revolve and Mirror** (rest of P-05, part of P-11) | B2 shaft revolved from a section sketch; a symmetric part mirrored |
| H-17 | P1 | L | todo | **Timeline bar** (P-07): features left to right under the view, roll-back marker, edit, suppress, failure shown in red | Roll back, insert a feature, roll forward: the part rebuilds |
| H-18 | P1 | M | todo | **3D Sketch tools**: 3-point and tangent arcs, trim/extend, offset, corner fillet, project a scan section (P-09) | The housing profile drawn with tangent arcs and filleted corners, fully constrained |
| H-19 | P1 | M | todo | **Deviation tools** (S-17 / RE-09): probe (value under the pointer), legend range and tolerance controls, a short PDF/HTML report | Hovering the bracket's map reads values; report lists RMS, max, % within |
| H-20 | P2 | S | todo | Undo/redo say "Nothing to undo/redo"; Edit menu shows "Undo <name>" (UX-21) | Ctrl+Z on an empty stack says so |
| H-21 | P2 | S | todo | **Calmer panels**: the hint paragraph collapses to one line with "More"; the primary button always bottom-right | Panel screenshots: no more than one line of text above the first control |
| H-22 | P2 | M | todo | **Sample scan and guided tour** (UX-18): Help > Open Sample loads the bracket scan; a 6-step tour over Getting Started | A newcomer reaches a STEP file from the sample without the guide |
| H-23 | P2 | S | todo | **Face From Curves / Loft warnings**: say when the result strays far from the scan (e.g. the loop crosses an edge of the part) | Housing-top loop over an edge: the message names the max deviation and suggests splitting the loop |
| H-24 | P1 | S | todo | **Run the usability scripts before each release** (absorbs UX-25 partly): s1-s6, trim, resize; results kept in `docs/plan/` | A run log and screenshots per release |

## Track U - UX foundations

Principles and findings: [UX_AUDIT.md](UX_AUDIT.md).

### Slice A (first UX pass)
| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| UX-02 | P0 | S | done | Scene tree shows only categories that have content; no section plane exists before a model is open | Empty project shows a single hint row, not 14 folders. A new category appears the first time an item is created. Existing scene-model tests updated. |
| UX-04 | P0 | S | done | Command palette on Ctrl+K and View menu; searches label, description, category; shows shortcut | Ctrl+K opens and focuses it; typing "loft" lists loft actions; Enter runs the first enabled one; Esc closes. |
| UX-06 | P0 | M | done | Tooltips for every toolbar/menu action: description + shortcut + *why it is disabled* | Hovering a disabled "Compute Section" with no model says "Needs: a loaded model". Reasons come from `ActionCondition`, not hard-coded strings. Every registered action has a non-empty tooltip (test). |
| UX-12 | P0 | S | done | One message area in the status bar plus a separate tool-hint area; no triplicated text; idle state shows model name, units, triangle count | Status bar never shows the same text twice; idle shows e.g. `part.stl - mm - 327,680 triangles`. |
| UX-01 / UX-11 | P0 | M | done | Properties panel when nothing is selected becomes a **Model & Next steps** panel: empty state with *Open scan* / recent files; once a model exists, a model summary and the next sensible actions as buttons | No model: "Open a scan" button, supported formats, recent projects. Model loaded, no sections: "Add a section plane" and "Compute section" buttons. Curves exist: "Loft between curves". BREP exists: "Export STEP". Each button dispatches the existing action and is disabled with a reason when not applicable. |
| UX-03 | P0 | S | done | Drag-and-drop `.stl/.obj/.ply/.openretop` onto the window; recent files list | Dropping a mesh runs the normal import flow (including the unit prompt); dropping a project opens it; other extensions are rejected with a message. |
| UX-09 | P1 | S | done | View shortcuts: Home = Frame All, F = Frame Selected, Ctrl+1/3/7 = Front/Right/Top (Ctrl+Shift for opposite), 0 = Isometric | Conflict check (`shortcut_conflicts`) is empty; documented in the cheat sheet. |
| UX-16 | P2 | S | done | Fix the Properties header/"Diagnostics" overlap | Screenshot comparison in a test or manual check recorded in the commit. |
| UX-26 | P0 | S | done | Selections made in the viewport (picks) now update the Scene tree and Properties panel; the Properties panel no longer paints stale group boxes | Pick a curve in the viewport: tree row highlights, inspector shows its fields (`tests/test_ux_selection_sync.py`). Found while verifying UX-16. |

| UX-27 | P0 | M | done | **View gizmo** replaces the old axes arrow and triangle buttons ([before](img/gizmo_before.png), [after](img/view_cube_in_app.png)): a glass view cube (FRONT/BACK/LEFT/RIGHT/TOP/BOTTOM labels, every face, edge and corner clickable = 26 views) combined with Blender-style XYZ axis balls (solid +X/+Y/+Z with letters, muted negative ends; clicking one looks along that axis), hover highlight and tooltips. No home/roll buttons (removed after review: they cluttered the gizmo); Isometric and Roll View stay in the View menu and Ctrl+K | Behaviour covered by `tests/test_view_cube.py` (all 26 regions reachable, labels never mirrored, ball hit-testing and occlusion, 2x DPI image). Verified in the running app with real mouse clicks (edge, corner, axis ball) and at 4x zoom: the overlay image is pixel-aligned, so glyph rows are even (a half-pixel offset had made head-on labels look jagged and skewed in the live window while offscreen renders looked fine). Drawn into the VTK frame (a Qt image shown by an overlay renderer) so it does not depend on Qt drawing over the native GL surface. `show_viewcube` controls the cube and buttons, `show_axis_gizmo` the axis balls. |

### Slice B
| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| UX-28 | P2 | S | todo | Animate view changes from the cube (about 250 ms ease between the old and new camera orientation) instead of cutting | Orientation interpolates via quaternion slerp; frame time stays under the 16 ms budget on a 300k-triangle scan; disabled by a setting. |
| UX-29 | P2 | M | todo | Drag on the cube to orbit; arrow buttons for 90 degree steps; perspective/orthographic toggle on the cube | Dragging the cube orbits the camera exactly like a viewport orbit; the toggle updates `ParallelProjection` and the tooltip. |
| UX-10 | P0 | L | todo | Workspaces + stepper: Scan, Sections, Curves, Surfaces, Export. A workspace sets the toolbar, expanded tree categories and Next-steps content | Switching workspace changes toolbar contents; the stepper marks steps that have results; works without any renderer setting. |
| UX-05 | P1 | M | todo | Restructure menus by task (File, Edit, View, Scan, Sections, Curves, Surfaces, Tools, Help); manual-curve point editing becomes a submenu that appears only while that tool is active; Modify's 90 entries are split | No menu above ~25 entries; every action reachable from either a menu or the palette; test asserts every registered action appears in exactly one menu or is palette-only by an explicit allow-list. |
| UX-07 | P1 | M | done (VIS-02) | Toolbar: icons, separators, grouping per workspace, `Compute Section` present | Every toolbar action has an icon and tooltip; groups separated. |
| UX-08 | P1 | S | todo | Vocabulary pass over labels and tree categories (see F-09) with a glossary tooltip for retained technical terms | No label in the audit's jargon list remains; docs updated. |
| UX-13 | P1 | M | done (VIS-05) | On-canvas tool hint overlay while Region / Manual Curve / Transform are active | Overlay text matches the tool's instructions and disappears when the tool ends. |
| UX-14 | P1 | M | todo | Richer inspector: mesh bounds in model units, source and display triangle counts, watertight flag, weld count; curve fit tolerance/error; contextual buttons | Values come from existing state; mesh selection shows `extent` with unit. |
| UX-15 | P1 | M | todo | Non-modal notifications with a "Details" expander and an activity log panel; actionable error text | Import failure shows a toast with the reason and suggestion; the log keeps the last 200 events. |
| UX-17 | P1 | M | todo | Help > Mouse & Keys cheat sheet that reflects the *active tool*; optional first-run tour (4 steps) | Cheat sheet shows the mapping for the current tool; tour can be dismissed and not shown again (setting). |
| UX-19 | P1 | M | todo | Autosave + crash recovery: periodic snapshot beside the project, offered on next start | Kill the process during an edit; restart offers recovery; clean exit removes the snapshot. |
| UX-21 | P1 | S | todo | Confirm destructive actions; Edit menu shows "Undo <name>" / "Redo <name>" | Delete Mesh and Clear All Sections ask first; the undo label is the command name. |
| UX-22 | P1 | M | todo | **Multi-section**: "Add N sections between min and max along axis" plus "Compute all" | A dialog creates N evenly spaced planes in one undo step; sections compute in one background task with progress. |
| UX-18 | P2 | S | todo | File > Open Sample (generated mesh) for learning | Opens without a file dialog and demonstrates the full workflow. |
| UX-20 | P2 | M | todo | UI scale setting and a light theme | Settings round-trip; widgets legible at 100/125/150%. |
| UX-23 | P2 | M | todo | Viewport hover highlight and selection outline; consistent colours per object type | Hovering a curve/surface highlights it; selected objects get an outline. |
| UX-24 | P2 | M | todo | Keyboard navigation and accessible names for all custom widgets | Tab order covers docks; every control has an accessible name (test). |
| UX-25 | P1 | S | todo | Usability script: "scan to STEP in 10 minutes" with timing and a notes template; run with at least three people | Results table added to `docs/plan/`; findings feed new UX tasks. |

---

### Slice C - viewport behaviour (owner requests)
| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| UX-33 | P0 | S | done | **Section plane only with the Section tool.** The default "Section Plane 1" is not drawn (viewport) or listed (tree) until the user engages the Section tool (Add Section Plane, Compute Section, selecting a plane). Esc, another tool, or selecting something else leaves the tool and hides the plane again. The plane stays in the data model so Compute still works. Also resolves BUG-08. | Open a scan: no plane in the viewport or tree. Click Compute Section: plane appears, section is cut. Esc: plane hides, section curves remain. Tests cover enter/leave rules and that Compute works from a fresh scan. |
| UX-30 | P0 | M | done | **Transform lines draw over everything, and only while grabbing.** The move axes and rotation rings render in an overlay layer with the depth buffer cleared (never hidden inside or behind the scan or the grid) and are visible only while a Move/Rotate is active; selecting an object must not show them. | With a transform active the axis lines are visible when they pass through the scan; after confirm/cancel/Esc or on a plain selection no transform prop is visible. Pixel/actor-level test: overlay renderer layer above the scene, depth not preserved, not part of the main renderer's props. |
| UX-31 | P1 | M | done | **Adaptive grid.** The grid is currently a static 10x10 square sized from the scene bounds. Replace with a grid that follows the camera: spacing snaps to 1-2-5 steps of the project unit as you zoom, minor and major lines, extends past the view and recentres as you pan, fades with distance, with coloured X/Y axis lines through the origin, and the current spacing shown in the status bar (for example `grid 10 mm`). | Zooming from far to near changes the spacing in 1-2-5 steps and the status text; panning keeps the grid under the view; geometry is rebuilt only when the spacing or snapped centre changes (counted in a test); never a visible rescale while an object is dragged. |
| UX-32 | P0 | L | done | **Measure tool for imported scans.** Click two points on the mesh to get the distance in project units (with the X/Y/Z components) drawn as a labelled line over the scene; several measurements can stay on screen and Esc or Clear Measurements removes them. Also a one-click "Model size" readout (bounding box X x Y x Z). Lets the user verify a scan came in at the right size and units. | On a mesh of known size the measured distance matches the true value (test uses a cube of known edge length in mm and in inches); the readout is in the project's units; measurements are not saved into the project file; the tool appears in the menu, the palette and the Next-steps panel. |
| UX-34 | P0 | S | done | **Axis and plane locks while grabbing** (Blender keys). During Move/Rotate: X, Y, Z lock to that world axis (press again to unlock); Shift+X/Y/Z lock to the plane that excludes it (Shift+Z = move on the floor). Changing the lock moves the object at once. A locked axis is drawn as a long coloured guide line through the object (two lines for a plane) and the free arrows are dimmed. While rotating, a plane lock rotates around the excluded axis. The controller always supported axis constraints, but no key was wired to them (the hint even said "type X, Y or Z"). | `tests/test_transform_locks.py`: each lock keeps the other coordinates exactly fixed; a floor lock seen from above equals a free move; an edge-on plane never jumps (clamped solve); the keys are bound and only active during a grab; cancel restores. Verified in the real window with real key presses (G, X, Shift+Z, Enter, then X outside a grab does nothing). |
| UX-35 | P1 | S | done | **Type a value while grabbing** (Blender style): G X 10 Enter moves exactly 10 project units along X; R Z -45 Enter rotates -45 degrees. Digits, `-`, `.` and Backspace edit the value (shown in the status bar); with no lock it applies along X, a lock redirects it, Backspace to empty hands back to the mouse. Digits are claimed from shortcuts only during a grab (so `0` does not switch to Isometric), and starting a grab focuses the viewport so the tree never swallows the keys. | `tests/test_transform_locks.py`: exact results (1e-12), undo restores, malformed input ignored, value dropped when the grab ends. Verified live with real keys starting from focus in the tree. |

### Slice D - visual design (owner: "the visuals are progressing, but still ugly")
Direction: Plasticity/Blender-like. Quiet charcoal chrome that steps back, one blue accent, the viewport as the brightest thing on screen. Before/after: [before](img/vis_before.png), [after](img/vis_after.png).

| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| VIS-01 | P0 | M | done | **Theme foundation**: design tokens (`workbench_ui/theme.py`: three surface elevations, two text levels, one accent, axis colours, light and dark sets) and a complete stylesheet for every widget in use (docks, menus, toolbar, buttons incl. a filled primary button, inputs, checkboxes, combos, property sections as headings with a hairline instead of boxed frames, tree rows, thin scroll bars, status bar, tooltips). Inline colours removed from the Next-steps panel. | Test: every widget selector is styled, every referenced asset exists, both themes define every token. Screenshots of the start screen, a loaded scan, a selection and a tool. |
| VIS-03 | P0 | S | done | **Viewport look**: smooth crease-aware shading (point normals split above 40 degrees, so scans read as surfaces and machined edges stay sharp; triangle order preserved for picking), satin material, key/fill/back/head studio lights, background as a soft vertical gradient from the background setting; selection box in the accent colour. | `tests/test_viewport_look.py` (triangle order, smooth sphere normals, sharp cube corners, gradient, lights idempotent). Normals cost 23 ms at 82k and 90 ms at 328k triangles, once per geometry change (drags only move the transform). |
| VIS-02 | P0 | M | done | **Toolbar with icons** (absorbs UX-07): a line-icon set drawn for the app (`workbench_ui/icons.py`, SVG with a colour placeholder, rendered at 1x/2x in the theme's text colours with a separate disabled pixmap, repainted on theme change); short labels under the icons (menus keep full names); five groups: file, history, view, transform, scan tools; Compute Section added as "Cut Section". | `tests/test_toolbar_icons.py`: every icon renders, disabled is dimmer, every button has an icon, a short label and a tooltip, four separators; 1151 px wide with Segoe UI 9 pt, so it fits 1280 px. |
| VIS-04 | P1 | M | partly done | **Panels**: scene tree icons per object type and one "Scene" header instead of three (done: header hidden, kind icons, the root row names the project); dock title bars with proper icon buttons; Next-steps as cards; consistent 8 px rhythm (todo). | `tests/test_ux_scene_tree.py`: rows have kind icons, no header, root follows the saved project name. |
| VIS-05 | P1 | S | done | **On-canvas tool hint** (absorbs UX-13): the active tool's instructions as a floating pill centred at the bottom of the viewport instead of a second status-bar copy. Painted by Qt into an image and drawn by a VTK overlay renderer (Qt widgets cannot draw over the native GL window), re-laid out on resize, wraps long hints, 2x sharp on high-DPI. The image overlay used by the view cube moved to `overlay_layers.ImageOverlay` and is shared. | `tests/test_ux_status_bar.py`: hint shown only while a tool is active, never duplicated in the status bar, wraps to the view width, scales with the device pixel ratio. |

## Bugs found by using the app

Reported by the project owner after running the v3 viewport. A/B-measured against Codex's original v3 (`c2ed867`) and my branch: every item below except BUG-08 is **inherited from the v3 viewport, not introduced by the refactor**. The original (Tk) app on `main` behaves correctly in these respects, so it is the reference.

| ID | Sev | Status | Finding | Fix / test |
|---|---|---|---|---|
| BUG-01 | S1 | fixed | Move/Rotate started with the pointer reference at (0, 0) (`payload.get("mouse_start", (0, 0))` and nothing supplied it), so the object jumped by the pointer's absolute screen position on the first mouse move (measured: 207 degrees of spin and a 4-8x overshoot). The Tk app uses `_last_viewport_mouse`. | Viewport tracks `last_pointer_position`; the window passes it as `mouse_start`. `tests/test_object_motion.py` |
| BUG-02 | S1 | fixed | Vertical axis inverted: VTK pointer coordinates are y-up but the transform maths (ported from Tk) is y-down, so dragging down moved the object up. | `to_widget_position` converts before the transform; test fails if the flip is removed. |
| BUG-03 | S1 | fixed | Every pointer event during a drag rebuilt the whole UI (tree, inspector, next-steps) - 30-65 ms per event, the "stutter". VTK rendering itself is about 2 ms. | `_render_scene()` re-renders only the 3D scene during a drag; panels refresh on confirm/cancel. 32 ms to 3 ms per event. |
| BUG-04 | S2 | fixed | The grid is sized from the scene bounds, so dragging an object away rescaled the grid every frame, which looked like the camera moving (the camera itself does not move; verified). | Grid size is held while a transform is active. |
| BUG-05 | S2 | fixed | Drag sensitivity used the scene's visible bounds, which grow as the object moves, so the drag accelerated. Tk used the model's own bounds. | Uses the model's own bounds. |
| BUG-06 | S1 | fixed | No selection bounding box (the Tk app draws one around the selected scan), so selecting gave no visible feedback. | `presentation/qt/selection_overlay.py`; follows the object while it moves. |
| BUG-07 | S2 | fixed | Clicking empty space did not deselect. | A click (not a drag) on empty space clears the selection. |
| BUG-08 | S3 | fixed (UX-33) | The white square in the middle of the grid is the default **Section Plane 1** outline. It is drawn at full white and reads as a stray object. Needs a decision: dimmer/translucent, or drawn only when the Sections step is active (UX-10). | |
| BUG-09 | S3 | fixed | While dragging, the Properties panel still showed the old Location/Rotation until the transform was confirmed (a consequence of BUG-03's fix). The fields were also one text line of raw floats (`0.7483314773547883, 0.0, 0.0`). | Vectors are three labelled X/Y/Z number boxes (3 decimals, axis colours); `PropertyInspectorWidget.show_values` updates them in place during a drag (no rebuild, no signals, a box being typed in is left alone). `tests/test_property_editors.py`, `test_the_properties_panel_follows_the_drag_without_being_rebuilt`. |
| BUG-12 | S1 | fixed | **Manual curve points and the curve being drawn were invisible.** The v3 viewport built the tool preview into every scene snapshot but nothing drew it (inherited from Codex's v3; the Tk app drew it in a layer above the scan). | `tool_preview_overlay.py`: fitted curve, a rubber-band line to the cursor and control points as shaded spheres (corner / smooth / selected / cursor colours from the display settings) over the scene. Spheres are real geometry kept at a constant screen size, because VTK's points-as-spheres draws 0 px on this GPU (measured). `tests/test_tool_rendering.py`. |
| BUG-13 | S1 | fixed | **Finished curves on a scan were mostly hidden.** The spline through the clicked points was never projected back onto the scan ("Keep Curve On Mesh" was off by default, and in v3 only reachable from a menu), so it cut through the inside of a curved scan (measured: up to 1.37 mm deep). Curves exactly on the facets also lost the depth test to them. | Curves drawn on a scan now follow its surface by default (0.000 mm); curves drawn off the scan are left alone. Coincident-topology offsets on, curve and section lines pulled towards the camera, regions pulled in front of the scan. Mutation-checked. |
| BUG-14 | S1 | fixed | **Pressing R zoomed the camera out** when Rotate was unavailable: the key fell through to VTK's built-in key bindings ("r" resets the camera; "w"/"s" wireframe/surface, "e"/"q" close the window, "3" stereo, "f" fly-to). | VTK's single-letter keys are disabled at the interactor style (`disable_vtk_key_bindings`). |
| BUG-15 | S2 | fixed | **In the Section tool, G/R did nothing** unless the plane was also selected, though the tool's own hint says "G moves and R rotates the plane". | While the Section tool is engaged, Move/Rotate act on the active plane. |
| BUG-11 | S2 | fixed | Selecting the scan made the main window grow taller (800 to 864 px, never shrinking back): the inspector was shown before the Next-steps panel was hidden, so for one layout pass both were in the Properties dock. | The outgoing panel is hidden first, and the Properties dock scrolls instead of growing. Verified live across repeated selections; the window can now be resized down to 500 px. |
| BUG-10 | S2 | fixed | The move arrows stayed at the world origin while the object moved away: `vtkAxesActor` ignores `SetPosition` when it draws (only a user transform reaches its parts). Found in the live check for UX-34. | Placed with a user transform; `MoveArrowPlacementTests` renders the arrows and fails if they do not move (or move twice). |

## Track R - architecture roadmap (from the ChatGPT roadmap, re-sequenced)

Rationale and disagreements: [ROADMAP_REVIEW.md](ROADMAP_REVIEW.md). None of these may
change visible behaviour until R-06.

| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| R-01 | P1 | M | todo | `ViewportHost` between the window and the viewport; the window no longer reaches into VTK-specific members | Window code references only the host interface; existing viewport tests pass unchanged. |
| R-02 | P1 | M | todo | Extract `VTKViewportBackend` behind a `ViewportBackend` contract (attach, close, synchronize(snapshot), frame, camera, pick, set_selection, render, capabilities) | `QtSceneViewport` delegates to the backend; a fake backend can drive the window in tests. |
| R-03 | P1 | S | todo | `ViewportCapability` model and a capability report per backend | Window asks capabilities instead of assuming; unit tests for the VTK report. |
| R-04 | P1 | S | todo | `CameraState` (position, focal point, up, projection, scale, fov) with VTK translation both ways and a "Link cameras" option for later | Round trip VTK -> state -> VTK reproduces the view within tolerance. |
| R-05 | P1 | L | todo | `BrepRenderItem` + persistent topology IDs: openRetop face/edge IDs <-> `TopoDS` subshapes <-> tessellation triangle ranges; IDs survive a rebuild when the source curves are unchanged | Test: build a loft, read face/edge IDs, rebuild, IDs match; tessellation exposes `face_id` per triangle. |
| R-06 | P1 | M | todo | VTK face/edge/vertex picking and highlighting from the topology IDs; selection modes in the UI | Clicking a loft face selects "Face N" in the tree/inspector; edges selectable; frame-selected works. |
| R-07 | P2 | M | todo | **OCCT viewport spike** (time-boxed, 1 week) with written go/no-go: embed `V3d_View` in PySide6, display a STEP, orbit/pan/zoom, pick a face | Report in `docs/plan/` with Windows + Linux results. No further OCCT viewport tasks until a *go*. |
| R-08 | P2 | M | todo | Per-viewport renderer override (advanced setting) | Only after R-07 go; otherwise cancelled. |
| R-09 | P2 | L | todo | Split view with two synchronized viewports (shared `CameraState` and selection IDs); scan reference vs reconstruction | Orbiting one rotates the other; selecting in one highlights in both. |
| R-10 | P2 | L | todo | Mesh repair workspace: components, island delete, holes, normals, non-manifold diagnostics, simplify | Each operation undoable and shown in the Next-steps panel. |
| R-11 | P2 | L | todo | Alignment workspace: datum / 3-2-1, point pairs, ICP, deviation colouring | ICP converges on a synthetic displaced scan within a stated tolerance. |
| R-12 | P2 | L | todo | Print-prep workspace: cut planes, segmentation, connectors, wall analysis, STL/3MF export | Splitting a box into two parts exports two watertight meshes. |
| R-13 | P2 | L | todo | CAD depth: guide-rail lofts, four-boundary patches into BREP, trims, intersections, sewing, shells/solids, booleans, fillets | Each is a separate task with a STEP round-trip test; kernel stays CadQuery/OCP unless a blocker is documented (no build123d switch planned). |

---

## Track E - engineering debt

| ID | P | Size | Status | Task | Acceptance |
|---|---|---|---|---|---|
| E-01 | P0 | M | todo | Region selection on the **source** mesh (map to display proxy for drawing) | Region triangle indices refer to the source mesh; a >150k-triangle mesh selects the same face as the full mesh; boundary extraction uses source geometry. |
| E-02 | P1 | M | todo | Multiple regions per project | Several regions persisted, listed in the tree, individually selectable and deletable. |
| E-03 | P1 | M | todo | Split `application/manual_curve_controller.py` (1.7k lines) by concern | No file over ~600 lines; behaviour tests unchanged. |
| E-04 | P1 | M | todo | Split `application/brep_controller.py` (1.5k) | As above. |
| E-05 | P1 | M | todo | Move model builders (`_scene_nodes`, `_inspector_fields`, `_surface_previews`) and file lifecycle out of `main_window.py` | Window under ~1,000 lines; builders unit-tested without widgets. |
| E-06 | P1 | L | todo | Clear mypy `ignore_errors` modules one by one | List in `pyproject.toml` shrinks every release; CI keeps new modules clean. |
| E-07 | P2 | S | todo | Tiny-curve thresholds in project units | `CURVE_TINY_MIN_*` derived from `geometry.tolerances`. |
| E-08 | P1 | M | todo | Large-scan performance (1M-5M triangles): memory-lean loader, background proxy build, section prefilter by bounding slab | 2M-triangle STL opens in a stated time budget with the UI responsive; benchmark recorded. |
| E-09 | P2 | S | todo | DPI-independent assertion in the navigation-widget pixel test | Passes at 100%, 125% and 150% scaling. |
| E-10 | P2 | M | todo | Run the visible-Windows UI tests in CI (self-hosted or scheduled) | Job exists and is green or tracked. |
| E-11 | P2 | S | todo | CadQuery compatibility matrix for the STEP unit argument and loft API | Tested against the pinned version and the next minor release. |
| E-12 | P2 | S | todo | Benchmarks with regression thresholds in CI (sections, adjacency, load) | CI fails on a >2x slowdown of the recorded baseline. |

---

## How tasks are run
1. Pick the top `todo` task in the slice being worked.
2. Write the failing test (or script the real-app check for pure-UI work).
3. Implement; run `ruff check .`, `mypy`, and the full suite.
4. Check the behaviour in the real app and note it in the commit message.
5. Flip the status here in the same commit.
