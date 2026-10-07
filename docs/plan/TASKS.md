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
| UX-07 | P1 | M | todo | Toolbar: icons, separators, grouping per workspace, `Compute Section` present | Every toolbar action has an icon and tooltip; groups separated. |
| UX-08 | P1 | S | todo | Vocabulary pass over labels and tree categories (see F-09) with a glossary tooltip for retained technical terms | No label in the audit's jargon list remains; docs updated. |
| UX-13 | P1 | M | todo | On-canvas tool hint overlay while Region / Manual Curve / Transform are active | Overlay text matches the tool's instructions and disappears when the tool ends. |
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
| UX-35 | P1 | S | todo | **Type a value while grabbing** (Blender style): G X 10 Enter moves exactly 10 project units along X; R Z 90 Enter rotates 90 degrees. Digits, `-`, `.` and Backspace edit the value, shown in the status bar and next to the object. | Typed value overrides the mouse until cleared; works with every lock; result exact to 1e-9; undo restores. |

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
| BUG-09 | S3 | open | While dragging, the Properties panel still shows the old Location/Rotation until the transform is confirmed (a consequence of BUG-03's fix; the status bar shows the live delta). | Update just the two transform fields during a drag if it is missed. |
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
